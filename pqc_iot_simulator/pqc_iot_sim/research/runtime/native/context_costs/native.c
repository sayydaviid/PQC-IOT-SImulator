/* Minimal blocking Python transport around native OpenSSL TLS 1.3.
 * Credentials and TLS session DER stay private to the experiment controller.
 * No custom TLS key schedule, cryptography, or signature verification.
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <openssl/ssl.h>
#include <openssl/err.h>
#include <openssl/sha.h>
#include <openssl/rand.h>
#include <openssl/core_names.h>
#include <openssl/params.h>
#include <stdint.h>
#include <openssl/pem.h>
#include <openssl/x509v3.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    SSL *ssl;
    unsigned long tx, rx, hs_tx, hs_rx;
    int cv_tx, cv_rx;
    char client_share[65], server_share[65];
    int cert_tx_n, cert_rx_n, cert_tx[8], cert_rx[8];
    int tickets_tx_n, tickets_rx_n, tickets_tx[32], tickets_rx[32];
    int session_plaintext_n, session_peer_cert_n, session_appdata_n;
    int client_session_der_n, offered_ticket_n, hello_n, psk_identity_n;

} Peer;

static void digest(const unsigned char *data, size_t n, char out[65]) {
    unsigned char md[32];
    SHA256(data, n, md);
    for (int i = 0; i < 32; i++) snprintf(out + i * 2, 3, "%02x", md[i]);
}

static void message(int write, int version, int type, const void *vbuf,
                    size_t length, SSL *ssl, void *arg) {
    Peer *p = arg;
    const unsigned char *b = vbuf;
    if (type == SSL3_RT_HEADER && length == 5) {
        unsigned long n = 5 + (((unsigned)b[3] << 8) | b[4]);
        if (write) p->tx += n; else p->rx += n;
    }
    if (type != SSL3_RT_HANDSHAKE || length < 4) return;
    if (b[0] == SSL3_MT_CERTIFICATE && length >= 8) {
        size_t pos = 5 + b[4];
        if (pos + 3 <= length) {
            size_t end = pos + 3 + (((size_t)b[pos] << 16) | ((size_t)b[pos+1] << 8) | b[pos+2]);
            pos += 3;
            while (pos + 3 <= end && end <= length) {
                size_t n = ((size_t)b[pos] << 16) | ((size_t)b[pos+1] << 8) | b[pos+2];
                pos += 3;
                if (pos + n + 2 > end) break;
                if (write && p->cert_tx_n < 8) p->cert_tx[p->cert_tx_n++] = (int)n;
                if (!write && p->cert_rx_n < 8) p->cert_rx[p->cert_rx_n++] = (int)n;
                pos += n;
                size_t ext = ((size_t)b[pos] << 8) | b[pos+1];
                pos += 2 + ext;
            }
        }
    }
    if (b[0] == SSL3_MT_NEWSESSION_TICKET && length >= 15) {
        size_t pos = 13 + b[12];
        if (pos + 2 <= length) {
            int n = ((int)b[pos] << 8) | b[pos+1];
            if (write && p->tickets_tx_n < 32) p->tickets_tx[p->tickets_tx_n++] = n;
            if (!write && p->tickets_rx_n < 32) p->tickets_rx[p->tickets_rx_n++] = n;
        }
    }
    if (b[0] == SSL3_MT_CLIENT_HELLO) p->hello_n = (int)length;
    if (b[0] == SSL3_MT_CERTIFICATE_VERIFY && length >= 6) {
        int code = ((int)b[4] << 8) | b[5];
        if (write) p->cv_tx = code; else p->cv_rx = code;
    }
    if (b[0] != SSL3_MT_CLIENT_HELLO && b[0] != SSL3_MT_SERVER_HELLO) return;
    /* Extract the public key_share extension, including group and length.
       The hash is public evidence of fresh shares, never a traffic secret. */
    size_t i = 4 + 2 + 32;
    if (i >= length) return;
    i += 1 + b[i];
    if (b[0] == SSL3_MT_CLIENT_HELLO) {
        if (i + 2 > length) return;
        size_t n = ((size_t)b[i] << 8) | b[i+1]; i += 2 + n;
        if (i >= length) return;
        i += 1 + b[i];
    } else i += 3;
    if (i + 2 > length) return;
    size_t n = ((size_t)b[i] << 8) | b[i+1]; i += 2;
    size_t end = i + n;
    if (end > length) return;
    while (i + 4 <= end) {
        int extension = ((int)b[i] << 8) | b[i+1];
        size_t size = ((size_t)b[i+2] << 8) | b[i+3]; i += 4;
        if (i + size > end) return;
        if (extension == 41 && b[0] == SSL3_MT_CLIENT_HELLO && size >= 4)
            p->psk_identity_n = ((int)b[i+2] << 8) | b[i+3];
        if (extension == 51) digest(b + i, size,
            b[0] == SSL3_MT_CLIENT_HELLO ? p->client_share : p->server_share);
        i += size;
    }
}

static PyObject *ssl_error(const char *operation) {
    unsigned long code = ERR_get_error();
    char error[256];
    ERR_error_string_n(code, error, sizeof(error));
    PyErr_Format(PyExc_OSError, "%s: %s", operation, error);
    return NULL;
}

static void free_context(PyObject *capsule) {
    SSL_CTX *ctx = PyCapsule_GetPointer(capsule, "tls.context");
    OPENSSL_clear_free(SSL_CTX_get_app_data(ctx), 80);
    SSL_CTX_free(ctx);
}
static void free_peer(PyObject *capsule) {
    Peer *p = PyCapsule_GetPointer(capsule, "tls.peer");
    SSL_free(p->ssl);
    PyMem_Free(p);
}

/* Same stateless ticket construction in both state policies. Only preservation
 * of the 80-byte STEK across gateway processes differs. Session/traffic key
 * derivation and ticket parsing/authentication remain in native OpenSSL.
 * Scoped experiment: one key epoch, lifetime 3600s, no deployment key rotation. */
static int ticket_key(SSL *ssl, unsigned char name[16], unsigned char *iv,
                      EVP_CIPHER_CTX *cipher, EVP_MAC_CTX *mac, int encrypt) {
    unsigned char *key = SSL_CTX_get_app_data(SSL_get_SSL_CTX(ssl));
    if (!key) return -1;
    if (encrypt) {
        Peer *p = SSL_get_app_data(ssl);
        SSL_SESSION *ss = SSL_get_session(ssl);
        if (p && ss) {
            p->session_plaintext_n = i2d_SSL_SESSION(ss, NULL);
            X509 *cert = SSL_SESSION_get0_peer(ss);
            p->session_peer_cert_n = cert ? i2d_X509(cert, NULL) : 0;
            void *data = NULL; size_t len = 0;
            SSL_SESSION_get0_ticket_appdata(ss, &data, &len);
            p->session_appdata_n = (int)len;
        }
        memcpy(name, key, 16);
        if (RAND_bytes(iv, 16) != 1 ||
            EVP_EncryptInit_ex(cipher, EVP_aes_256_cbc(), NULL, key + 16, iv) != 1)
            return -1;
    } else {
        if (CRYPTO_memcmp(name, key, 16) != 0) return 0;
        if (EVP_DecryptInit_ex(cipher, EVP_aes_256_cbc(), NULL, key + 16, iv) != 1)
            return -1;
    }
    OSSL_PARAM params[] = {
        OSSL_PARAM_construct_utf8_string(OSSL_MAC_PARAM_DIGEST, "SHA256", 0),
        OSSL_PARAM_construct_end()
    };
    if (EVP_MAC_init(mac, key + 48, 32, params) != 1) return -1;
    return 1;
}

static PyObject *context(PyObject *self, PyObject *args) {
    const char *cert, *key, *ca, *group, *sigalgs, *ticket;
    int server, include_root = -1;
    Py_ssize_t ticket_size;
    if (!PyArg_ParseTuple(args, "ssssisy#|i", &cert, &key, &ca, &group,
                          &server, &sigalgs, &ticket, &ticket_size, &include_root)) return NULL;
    if ((server && ticket_size != 80) || (!server && ticket_size != 0)) {
        PyErr_SetString(PyExc_ValueError, "server ticket key must have 80 bytes");
        return NULL;
    }
    SSL_CTX *ctx = SSL_CTX_new(TLS_method());
    if (!ctx) return ssl_error("SSL_CTX_new");
    if (!SSL_CTX_set_min_proto_version(ctx, TLS1_3_VERSION) ||
        !SSL_CTX_set_max_proto_version(ctx, TLS1_3_VERSION) ||
        !SSL_CTX_set_ciphersuites(ctx, "TLS_AES_256_GCM_SHA384") ||
        !SSL_CTX_set1_groups_list(ctx, group) ||
        !SSL_CTX_set1_sigalgs_list(ctx, sigalgs) ||
        !SSL_CTX_use_certificate_chain_file(ctx, cert) ||
        !SSL_CTX_use_PrivateKey_file(ctx, key, SSL_FILETYPE_PEM) ||
        !SSL_CTX_check_private_key(ctx) ||
        !SSL_CTX_load_verify_locations(ctx, ca, NULL)) {
        SSL_CTX_free(ctx); return ssl_error("TLS context");
    }
    /* Explicit wire chain, independent of the trust store. -1 reproduces the
       old automatic building, 0 sends leaf only, 1 sends leaf plus root. */
    if (include_root >= 0) {
        SSL_CTX_set_mode(ctx, SSL_MODE_NO_AUTO_CHAIN);
        SSL_CTX_clear_chain_certs(ctx);
        if (include_root) {
            BIO *in = BIO_new_file(ca, "r");
            X509 *root = in ? PEM_read_bio_X509(in, NULL, NULL, NULL) : NULL;
            BIO_free(in);
            if (!root || !SSL_CTX_add1_chain_cert(ctx, root)) {
                X509_free(root); SSL_CTX_free(ctx); return ssl_error("wire chain");
            }
            X509_free(root);
        }
    }
    SSL_CTX_set_verify(ctx, SSL_VERIFY_PEER | (server ? SSL_VERIFY_FAIL_IF_NO_PEER_CERT : 0), NULL);
    SSL_CTX_set_max_early_data(ctx, 0);
    SSL_CTX_set_timeout(ctx, 3600);
    SSL_CTX_set_options(ctx, SSL_OP_NO_COMPRESSION);
    if (server) {
        static const unsigned char sid[] = "iot-continuity-v2";
        unsigned char *material = OPENSSL_memdup(ticket, 80);
        if (!material) { SSL_CTX_free(ctx); return PyErr_NoMemory(); }
        SSL_CTX_set_app_data(ctx, material);
        if (!SSL_CTX_set_session_id_context(ctx, sid, sizeof(sid)-1) ||
            !SSL_CTX_set_tlsext_ticket_key_evp_cb(ctx, ticket_key)) {
            OPENSSL_clear_free(material, 80); SSL_CTX_free(ctx);
            return ssl_error("stateless ticket configuration");
        }
        SSL_CTX_set_session_cache_mode(ctx, SSL_SESS_CACHE_SERVER | SSL_SESS_CACHE_NO_INTERNAL_STORE);
        SSL_CTX_set_num_tickets(ctx, 1);
    } else SSL_CTX_set_session_cache_mode(ctx, SSL_SESS_CACHE_CLIENT);
    return PyCapsule_New(ctx, "tls.context", free_context);
}

static PyObject *handshake(PyObject *self, PyObject *args) {
    PyObject *capsule;
    int fd, server;
    const char *hostname, *der;
    Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "Oiisy#", &capsule, &fd, &server, &hostname, &der, &n)) return NULL;
    SSL_CTX *ctx = PyCapsule_GetPointer(capsule, "tls.context");
    if (!ctx) return NULL;
    Peer *p = PyMem_Calloc(1, sizeof(Peer));
    if (!p) return PyErr_NoMemory();
    p->ssl = SSL_new(ctx);
    if (!p->ssl) { PyMem_Free(p); return ssl_error("SSL_new"); }
    SSL_set_app_data(p->ssl, p);
    SSL_set_fd(p->ssl, fd);
    SSL_set_msg_callback(p->ssl, message);
    SSL_set_msg_callback_arg(p->ssl, p);
    if (server && !SSL_set1_host(p->ssl, "iot_1")) {
        SSL_free(p->ssl); PyMem_Free(p); return ssl_error("client identity");
    }
    if (!server) {
        if (!SSL_set1_host(p->ssl, hostname) || !SSL_set_tlsext_host_name(p->ssl, hostname)) {
            SSL_free(p->ssl); PyMem_Free(p); return ssl_error("server identity");
        }
        if (n) {
            const unsigned char *cursor = (const unsigned char *)der;
            SSL_SESSION *saved = d2i_SSL_SESSION(NULL, &cursor, n);
            if (!saved || cursor != (const unsigned char *)der + n ||
                !SSL_SESSION_is_resumable(saved) || SSL_SESSION_get_max_early_data(saved) != 0 ||
                !SSL_set_session(p->ssl, saved)) {
                SSL_SESSION_free(saved); SSL_free(p->ssl); PyMem_Free(p);
                return ssl_error("saved session");
            }
            const unsigned char *ticket_data = NULL; size_t ticket_len = 0;
            SSL_SESSION_get0_ticket(saved, &ticket_data, &ticket_len);
            p->offered_ticket_n = (int)ticket_len;
            SSL_SESSION_free(saved);
        }
    }
    int result;
    Py_BEGIN_ALLOW_THREADS
    result = server ? SSL_accept(p->ssl) : SSL_connect(p->ssl);
    Py_END_ALLOW_THREADS
    if (result != 1 || SSL_get_verify_result(p->ssl) != X509_V_OK) {
        SSL_free(p->ssl); PyMem_Free(p); return ssl_error("authenticated handshake");
    }
    p->hs_tx = p->tx; p->hs_rx = p->rx;
    return PyCapsule_New(p, "tls.peer", free_peer);
}

static PyObject *write_bytes(PyObject *self, PyObject *args) {
    PyObject *capsule; const char *data; Py_ssize_t n;
    if (!PyArg_ParseTuple(args, "Oy#", &capsule, &data, &n)) return NULL;
    Peer *p = PyCapsule_GetPointer(capsule, "tls.peer"); if (!p) return NULL;
    size_t written = 0; int result;
    Py_BEGIN_ALLOW_THREADS
    result = SSL_write_ex(p->ssl, data, n, &written);
    Py_END_ALLOW_THREADS
    if (!result) return ssl_error("SSL_write");
    return PyLong_FromSize_t(written);
}

static PyObject *read_bytes(PyObject *self, PyObject *args) {
    PyObject *capsule; int n;
    if (!PyArg_ParseTuple(args, "Oi", &capsule, &n)) return NULL;
    if (n < 1 || n > 65536) { PyErr_SetString(PyExc_ValueError, "invalid read size"); return NULL; }
    Peer *p = PyCapsule_GetPointer(capsule, "tls.peer"); if (!p) return NULL;
    PyObject *output = PyBytes_FromStringAndSize(NULL, n); if (!output) return NULL;
    size_t got = 0; int result;
    Py_BEGIN_ALLOW_THREADS
    result = SSL_read_ex(p->ssl, PyBytes_AS_STRING(output), n, &got);
    Py_END_ALLOW_THREADS
    if (!result) { Py_DECREF(output); return ssl_error("SSL_read"); }
    if (_PyBytes_Resize(&output, got) < 0) return NULL;
    return output;
}

static PyObject *session(PyObject *self, PyObject *args) {
    PyObject *capsule;
    if (!PyArg_ParseTuple(args, "O", &capsule)) return NULL;
    Peer *p = PyCapsule_GetPointer(capsule, "tls.peer"); if (!p) return NULL;
    SSL_SESSION *saved = SSL_get1_session(p->ssl);
    if (!saved || !SSL_SESSION_is_resumable(saved) || SSL_SESSION_get_max_early_data(saved) != 0) {
        SSL_SESSION_free(saved); Py_RETURN_NONE;
    }
    int n = i2d_SSL_SESSION(saved, NULL);
    p->client_session_der_n = n;
    if (n <= 0) { SSL_SESSION_free(saved); return ssl_error("session serialization"); }
    PyObject *output = PyBytes_FromStringAndSize(NULL, n);
    if (!output) { SSL_SESSION_free(saved); return NULL; }
    unsigned char *cursor = (unsigned char *)PyBytes_AS_STRING(output);
    i2d_SSL_SESSION(saved, &cursor); SSL_SESSION_free(saved);
    return output;
}

static PyObject *metadata(PyObject *self, PyObject *args) {
    PyObject *capsule;
    if (!PyArg_ParseTuple(args, "O", &capsule)) return NULL;
    Peer *p = PyCapsule_GetPointer(capsule, "tls.peer"); if (!p) return NULL;
    X509 *cert = SSL_get1_peer_certificate(p->ssl);
    const char *keytype = cert ? EVP_PKEY_get0_type_name(X509_get0_pubkey(cert)) : "NONE";
    const char *group = SSL_get0_group_name(p->ssl);
    PyObject *value = Py_BuildValue("{s:s,s:s,s:s,s:i,s:l,s:k,s:k,s:k,s:k,s:i,s:i,s:s,s:s,s:s}",
        "version", SSL_get_version(p->ssl), "cipher", SSL_get_cipher_name(p->ssl),
        "group", group ? group : "NONE", "reused", SSL_session_reused(p->ssl),
        "verify_result", SSL_get_verify_result(p->ssl), "tx_tls_bytes", p->tx, "rx_tls_bytes", p->rx,
        "handshake_tx_tls_bytes", p->hs_tx, "handshake_rx_tls_bytes", p->hs_rx,
        "certificate_verify_tx_scheme", p->cv_tx, "certificate_verify_rx_scheme", p->cv_rx,
        "peer_key_type", keytype, "client_share_sha256", p->client_share, "server_share_sha256", p->server_share);
    /* OpenSSL may not retain get0_peername on resumption. Match the recovered
       authenticated peer certificate as well, never the application payload. */
    const char *expected_name = SSL_is_server(p->ssl) ? "iot_1" : "gateway.local";
    const char *peername = cert && X509_check_host(cert,expected_name,0,0,NULL)==1 ? expected_name : "";
    PyObject *name = PyUnicode_FromString(peername ? peername : "");
    PyDict_SetItemString(value, "verified_peer_name", name); Py_DECREF(name);
    const char *keys[] = {"wire_cert_tx_der_bytes", "wire_cert_rx_der_bytes", "tickets_tx_bytes", "tickets_rx_bytes"};
    int *arrays[] = {p->cert_tx, p->cert_rx, p->tickets_tx, p->tickets_rx};
    int ns[] = {p->cert_tx_n, p->cert_rx_n, p->tickets_tx_n, p->tickets_rx_n};
    for (int j=0; j<4; j++) {
        PyObject *list = PyList_New(ns[j]);
        for (int k=0; k<ns[j]; k++) PyList_SET_ITEM(list,k,PyLong_FromLong(arrays[j][k]));
        PyDict_SetItemString(value,keys[j],list); Py_DECREF(list);
    }
    const char *ik[] = {"ticket_plaintext_session_der_bytes", "ticket_peer_certificate_der_bytes", "ticket_application_data_bytes", "client_session_der_bytes", "offered_ticket_bytes", "clienthello_handshake_bytes", "psk_identity_bytes"};
    int iv[] = {p->session_plaintext_n,p->session_peer_cert_n,p->session_appdata_n,p->client_session_der_n,p->offered_ticket_n,p->hello_n,p->psk_identity_n};
    for (int j=0;j<7;j++) {PyObject *n=PyLong_FromLong(iv[j]); PyDict_SetItemString(value,ik[j],n); Py_DECREF(n);}
    X509_free(cert); return value;
}

static PyObject *shutdown_peer(PyObject *self, PyObject *args) {
    PyObject *capsule;
    if (!PyArg_ParseTuple(args, "O", &capsule)) return NULL;
    Peer *p = PyCapsule_GetPointer(capsule, "tls.peer"); if (!p) return NULL;
    int result;
    Py_BEGIN_ALLOW_THREADS
    result = SSL_shutdown(p->ssl);
    Py_END_ALLOW_THREADS
    return PyLong_FromLong(result);
}

static PyMethodDef methods[] = {
    {"context", context, METH_VARARGS, NULL}, {"handshake", handshake, METH_VARARGS, NULL},
    {"write", write_bytes, METH_VARARGS, NULL}, {"read", read_bytes, METH_VARARGS, NULL},
    {"session", session, METH_VARARGS, NULL}, {"metadata", metadata, METH_VARARGS, NULL},
    {"shutdown", shutdown_peer, METH_VARARGS, NULL}, {NULL, NULL, 0, NULL}
};
static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "_context_tls", NULL, -1, methods,
                                  NULL, NULL, NULL, NULL};
PyMODINIT_FUNC PyInit__context_tls(void) { return PyModule_Create(&module); }
