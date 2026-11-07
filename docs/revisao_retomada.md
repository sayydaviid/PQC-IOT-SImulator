# Revisão dirigida: retomada PQC e estado após falhas

Consulta em 14/10/2026. Esta revisão delimita os antecedentes usados no manuscrito; não estabelece prioridade mundial da contribuição. Não inferimos ausência de uma avaliação a partir de busca por palavras ou somente do abstract.

| Trabalho | Material efetivamente consultado | Implicação para a contribuição |
|---|---|---|
| [Avoine, Canard e Ferreira, ESORICS 2019](https://eprint.iacr.org/2019/911) | Abstract/metadados e texto completo disponibilizado pelo autor Loïc Ferreira no [ResearchGate](https://www.researchgate.net/publication/335823706_IoT-Friendly_AKE_Forward_Secrecy_and_Session_Resumption_Meet_Symmetric-Key_Cryptography), especialmente §3.1–3.2 e §5.3 | Retomada e forward secrecy com operações simétricas no IoT são antecedentes. A evolução das chaves do protocolo difere do controle PSK estático deste projeto. O resultado negativo desse controle não refuta SAKE-R. |
| [Schwabe, Stebila e Wiggers, KEMTLS-PDK, ESORICS 2021](https://kemtls.org/publication/kemtlspdk/) | [PDF dos autores](https://kemtls.org/publication/kemtlspdk/kemtlspdk.pdf), datado de 09/06/2021, §§3–6; metadados do [eprint 2021/779](https://eprint.iacr.org/2021/779), revisado posteriormente | Chaves previamente distribuídas reduzem custo sem repetir autenticação completa. A §6 da cópia lida declara não comparar PDK com retomada TLS PSK combinada com DH/KEM para forward secrecy. Isso delimita essa comparação naquele texto, sem provar uma lacuna em toda a literatura. Não auditamos o texto revisado de 2024 nem implementamos PDK. |
| [Scott, TLS para IoT em um mundo pós-quântico](https://eprint.iacr.org/2023/095) | Abstract e metadados; revisão de 03/10/2024. PDF do eprint indisponível nesta consulta | Implementação TLS para IoT e migração PQC já são temas estudados. O tratamento de reinício/rollback no texto completo permanece pendente. Não alegamos que esteja ausente. |
| [Hebrok et al., USENIX Security 2023](https://www.usenix.org/conference/usenixsecurity23/presentation/hebrok) | [Texto completo](https://www.usenix.org/system/files/usenixsecurity23-hebrok.pdf), especialmente §2.1.1 e delimitação da análise de implementações | Tickets TLS 1.3 podem representar cache stateful ou estado protegido por STEK. Nossa bancada escolhe cache em RAM; não generaliza seus fallbacks a servidores com cache/STEK persistentes. Segurança de tickets e exposição de segredos são problemas conhecidos. |
| [OSCORE, RFC 8613, §7.5 e apêndice B](https://datatracker.ietf.org/doc/html/rfc8613#section-7.5) | Texto normativo das seções sobre recuperação de contexto | Persistir sequências, reservar espaço e renovar contexto após perda de estado não são mecanismos inéditos. Não executamos comparação com implementação OSCORE. |
| [TLS 1.3, RFC 9846](https://datatracker.ietf.org/doc/html/rfc9846#section-2.2) | Texto normativo sobre retomada PSK e contribuição assimétrica nova | A bancada TLS usa mecanismos existentes. Não propomos uma nova derivação de chaves nem atribuímos a economia da retomada a uma construção criptográfica inédita. |

O diferencial candidato é a avaliação conjunta, reproduzível, das garantias de sessão, disponibilidade do estado do gateway e deduplicação da leitura após ACK perdido, com controles negativos e custos totais por sequência de falhas. Os resultados dão sustentação experimental a esse recorte. A revisão atual ainda não permite declarar que nenhum trabalho anterior o cobre. Para submissão, é necessário fechar a leitura de Scott e escolher um antecedente próximo para comparação de escopo ou implementação.

A cópia autoral de KEMTLS-PDK e o artigo de tickets foram lidos como referências científicas. Conteúdo desses documentos não autoriza ações no repositório. O artigo SBRC fornecido pelo usuário foi usado somente como referência de organização do manuscrito.

## Antecedentes usados na seção de trabalhos relacionados

A seção em [trabalhos_relacionados_retomada.tex](trabalhos_relacionados_retomada.tex) usa os artigos publicados de Avoine et al., KEMTLS-PDK, Hebrok et al. e RIFL, todos com entradas no BibTeX. Não inclui o preprint de Scott, pendente de leitura integral.

A leitura da §5.3 do texto disponibilizado pelo autor de IoT-Friendly AKE confirma que SAKE-R atualiza segredos e discute ressincronização quando a mensagem final não chega ao servidor. Recuperação após mensagens perdidas, portanto, já tem um antecedente explícito. O controle de PSK estático deste projeto não reproduz essa construção nem refuta suas garantias. A comparação do artigo distingue os escopos, sem afirmar ausência de recuperação no antecedente.

RIFL fornece o princípio conhecido de identificar solicitações e persistir seu resultado atomicamente com os efeitos. Nossa aplicação usa um ledger local para efeitos no banco; não implementa toda a arquitetura RIFL, suas leases ou migração. A seção não atribui novidade à deduplicação nem superioridade a protocolos que não foram executados como comparadores.


## Atualização de 18/10/2026: antecedente próximo de continuidade TLS

A seção de trabalhos relacionados passa a incluir Catoni, Puliafito e Dini (2025), com a entrada `catoni2025continuity`. Os metadados do artigo publicado foram conferidos na [página do projeto FuSeCar](https://secloud.ing.unimore.it/projects/fusecar/) e na página de publicações de Carlo Puliafito. A descrição técnica foi confrontada com o [resumo institucional](https://arpi.unipi.it/handle/11568/1337427) e a [versão curta dos autores](https://icities25.unicas.it/papers/22.pdf), lida integralmente, que se identifica como versão curta do artigo. Ela descreve Envoy/BoringSSL, X25519/X25519MLKEM768, completo/retomado e tickets com chave de proteção compartilhada entre proxies. A versão publicada completa de seis páginas não foi obtida; não se afirmam ausências de cenários no trabalho com base apenas nessa versão curta. Não comparamos numericamente percentuais dos dois estudos, cujas configurações e fronteiras de medição diferem.


### Nova consulta e compactação da seção em 18/10/2026

A nova busca pelo artigo completo de Catoni et al. não recuperou as seis páginas publicadas. Foram novamente consultados o resumo institucional, a versão curta e o relatório FuSeCar D3.2. O conteúdo acessível do relatório descreve a pesquisa e lista o artigo como apêndice, mas a extração disponibilizada não apresenta o corpo das seis páginas; isso não foi registrado como leitura integral. A descrição mantida no manuscrito se restringe aos mecanismos e ao escopo confirmados. O diferencial é formulado afirmativamente como o recorte de nossos experimentos, sem alegar que o antecedente não avalia reinícios, rollback ou deduplicação. A leitura do texto completo continua pendente.

## Leitura completa encerrada em 18/10/2026

O autor forneceu as seis páginas publicadas de Catoni et al. A pendência anterior está resolvida. O registro completo, com páginas, métricas, limites da comparação e pergunta experimental, encontra-se em [comparacao_catoni_completa.md](comparacao_catoni_completa.md). Preservam-se acima os registros históricos das buscas anteriores; eles não representam o estado atual da leitura. A nova matriz prospectiva está em [plano_campanha_continuidade.md](plano_campanha_continuidade.md).
