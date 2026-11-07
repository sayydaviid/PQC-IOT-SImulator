/* Minimal blocking Python transport around native OpenSSL TLS 1.3.
 * Credentials and TLS session DER stay private to the experiment controller.
 * No custom TLS key schedule, cryptography, or signature verification.
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <openssl/ssl.h>
#include <openssl/err.h>
#include <openssl/sha.h>
#include <stdint.h>
#include <string.h>

typedef struct {
    SSL *ssl;
    unsigned long tx, rx, hs_tx, hs_rx;
    int cv_tx, cv_rx;
    char client_share[65], server_share[65];
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
    SSL_CTX_free(PyCapsule_GetPointer(capsule, "tls.context"));
}
static void free_peer(PyObject *capsule) {
    Peer *p = PyCapsule_GetPointer(capsule, "tls.peer");
    SSL_free(p->ssl);
    PyMem_Free(p);
}

static PyObject *context(PyObject *self, PyObject *args) {
    const char *cert, *key, *ca, *group;
    int server;
    if (!PyArg_ParseTuple(args, "ssssi", &cert, &key, &ca, &group, &server)) return NULL;
    SSL_CTX *ctx = SSL_CTX_new(TLS_method());
    if (!ctx) return ssl_error("SSL_CTX_new");
    if (!SSL_CTX_set_min_proto_version(ctx, TLS1_3_VERSION) ||
        !SSL_CTX_set_max_proto_version(ctx, TLS1_3_VERSION) ||
        !SSL_CTX_set_ciphersuites(ctx, "TLS_AES_256_GCM_SHA384") ||
        !SSL_CTX_set1_groups_list(ctx, group) ||
        !SSL_CTX_set1_sigalgs_list(ctx, "mldsa44") ||
        !SSL_CTX_use_certificate_chain_file(ctx, cert) ||
        !SSL_CTX_use_PrivateKey_file(ctx, key, SSL_FILETYPE_PEM) ||
        !SSL_CTX_check_private_key(ctx) ||
        !SSL_CTX_load_verify_locations(ctx, ca, NULL)) {
        SSL_CTX_free(ctx); return ssl_error("TLS context");
    }
    SSL_CTX_set_verify(ctx, SSL_VERIFY_PEER | (server ? SSL_VERIFY_FAIL_IF_NO_PEER_CERT : 0), NULL);
    SSL_CTX_set_max_early_data(ctx, 0);
    SSL_CTX_set_timeout(ctx, 3600);
    SSL_CTX_set_options(ctx, SSL_OP_NO_COMPRESSION | SSL_OP_NO_TICKET);
    /* Stateful TLS 1.3 tickets: a live server session cache is authoritative.
       Restarting this SSL_CTX drops it and forces an authenticated full flight. */
    if (server) {
        static const unsigned char sid[] = "pqc-iot-tls-v1";
        SSL_CTX_set_session_id_context(ctx, sid, sizeof(sid)-1);
        SSL_CTX_set_session_cache_mode(ctx, SSL_SESS_CACHE_SERVER);
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
static struct PyModuleDef module = {PyModuleDef_HEAD_INIT, "_pqc_tls", NULL, -1, methods,
                                  NULL, NULL, NULL, NULL};
PyMODINIT_FUNC PyInit__pqc_tls(void) { return PyModule_Create(&module); }
