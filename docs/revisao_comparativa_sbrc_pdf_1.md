# Revisão comparativa — nova versão do manuscrito

Data: 18/10/2026. Documento revisto após a atualização das seis seções. A revisão anterior foi preservada em `revisao_comparativa_sbrc_versao_anterior.md`.

## Parecer atual

A nova versão mantém a fórmula de organização do artigo aprovado e incorpora os principais ajustes de exposição da primeira revisão. A pergunta de pesquisa está explícita, as contribuições descrevem uma avaliação experimental, os trabalhos relacionados incluem um antecedente próximo e a conclusão destaca o tráfego da sequência completa de recuperação.

Eu manteria essa organização. Antes de considerar o texto uma versão de submissão, concentraria a revisão em três frentes: alinhamento do resumo ao resultado principal, delimitação da contribuição em relação aos antecedentes e compactação com correções locais de paginação. As alterações de redação realizadas melhoram a comunicação dos resultados; não estabelecem, por si, a novidade científica da integração.

## Material e procedimento

Foram lidos integralmente e inspecionados visualmente os dois PDFs fornecidos. As páginas citadas são posições no arquivo, não números impressos.

| Documento | Extensão | SHA-256 |
|---|---:|---|
| Atual: `sbrc_27_iot_corrigido (1).pdf` | 18 páginas | `e99c7e05d0a6c794318422e4e76d0aecda635612caca340052c3117a8d672e3a` |
| Aprovado: `5904_Versao_final_de_artigo_aceito (1).pdf` | 14 páginas | `02136fd741e43030f502a6757d93ae7ffcc3183a5ad6eba8e384065c678ed31a` |

Os percentuais de tráfego e os tempos destacados foram confrontados com `docs/resultado_tls_piloto.csv`. O registro de leitura dos antecedentes foi conferido em `docs/revisao_retomada.md`. Não houve novos experimentos, alteração dos dados ou edição dos PDFs nesta revisão. As afirmações do artigo aprovado não foram objeto de uma auditoria independente.

## 1. Comparação da estrutura

| Elemento | Artigo aprovado | Nova versão | Avaliação |
|---|---|---|---|
| Resumo e introdução | Contexto, desafios, proposta, avaliação e contribuições | Mesma sequência; pergunta de pesquisa explícita | Estrutura preservada |
| Fundamentação | Duas subseções principais, duas subsubseções, equações e Figuras 1–2 | Mesma hierarquia, cinco equações ligadas ao problema e Figuras 1–2 | Ajuste adequado ao novo domínio |
| Relacionados | Antecedentes e comparação com a proposta | Mesmo formato, agora com cinco trabalhos e Catoni et al. | Avanço em relação à versão anterior |
| Proposta | Modelagem, estratégia e Figura 3 | Mesma divisão; separação dos três estados necessários à recuperação | Estrutura preservada |
| Avaliação | Três subseções de resultados | Três campanhas: estado, interrupções e TLS | Correspondência clara com a pergunta |
| Conclusão | Resultados e trabalhos futuros | Mesma sequência, destacando tráfego por ensaio | Mais alinhada aos resultados |

A organização está resolvida. Não há necessidade de igualar a quantidade de equações, referências ou caracteres. O aspecto a reaproveitar do artigo aprovado é a ligação entre problema, contribuição e avaliação.

No trabalho de purificação, as decisões de ajustar rodadas, acrescentar recursos e reaproveitar pares tornam a estratégia identificável. No atual, o centro é caracterizar experimentalmente o comportamento de mecanismos existentes sob falhas. Esse enquadramento é coerente, mas exige mostrar qual conhecimento adicional emerge da avaliação e como ele se distingue dos antecedentes.

## 2. Ajustes anteriores que já aparecem no PDF

- **Pergunta de pesquisa e contribuições — p. 2:** a introdução agora relaciona explicitamente preservação de estado, custo e repetição de efeitos. As contribuições estão alinhadas ao que foi implementado e observado.
- **Fundamentação — pp. 3–6:** as definições genéricas foram condensadas. Permanecem as equações de custo, unicidade, exposição por reutilização, reserva de contadores e decisão sobre leituras.
- **Antecedente próximo — pp. 7–8:** Catoni et al. foi incluído e o texto reconhece a proximidade da retomada com troca híbrida. A comparação evita atribuir novidade à retomada isoladamente.
- **Limites do protótipo e do TLS — p. 9:** a instrumentação distingue a observação dos pares chave/nonce no protótipo da verificação de parâmetros e compartilhamentos públicos no TLS.
- **Condições experimentais — p. 14:** a Tabela 2 reúne parâmetros relevantes e a unidade de repetição está explicitada como bloco.
- **Figura 5 — pp. 13–14:** a continuação aparece antes do início da Subseção 5.3. O problema dessa transição foi corrigido.
- **Interpretação dos resultados — pp. 15–17:** os 87,96% são separados dos cerca de 55% da sequência completa; a condição com maior tempo de recuperação na retomada é reconhecida; a conclusão não promete melhora geral de latência.
- **Vocabulário:** journal, ledger e commit foram substituídos no corpo revisado por descrições compreensíveis. Nomes de mecanismos de implementação, como WAL, permanecem onde são pertinentes.

Não encontrei referências visivelmente não resolvidas, como `??`, no texto extraído, nem páginas vazias na inspeção visual. Isso não equivale a uma auditoria do log de compilação do Overleaf, que não foi fornecido.

## 3. Pendências de maior prioridade

### 3.1. Atualizar abstract e resumo — p. 1

A avaliação e a conclusão agora destacam a redução do tráfego IPv4 da sequência completa, mas abstract e resumo continuam apresentando somente os 87,96% do handshake e a deduplicação. O percentual do resumo está corretamente delimitado; o problema é o destaque incompleto do resultado principal de recuperação.

Sugestão de conteúdo para o resumo:

> Nos ensaios com deduplicação ativa, as reduções entre as medianas de tráfego IPv4 da sequência completa variaram de 55,43% a 55,57%. Com contexto disponível, a redução nos bytes do handshake foi de 87,96%.

O texto pode ser encurtado em outro ponto para preservar o tamanho desejado. O abstract deve apresentar a mesma distinção. Explicitar que o fallback após reinício corresponde à política de cache em memória da bancada também melhora a precisão.

### 3.2. Delimitar o valor científico da avaliação — pp. 2, 7–9 e 16–17

O texto está mais preciso ao reconhecer o uso de mecanismos conhecidos. A pendência é sustentar o diferencial frente a avaliações próximas, especialmente a de Catoni et al. Apenas utilizar TLS pós-quântico, reduzir certificados por retomada ou manter decisões no banco não estabelece uma contribuição inédita.

O argumento central deve identificar a combinação concreta de estados e falhas estudados, o que se mede em cada campanha e a consequência prática observada. Os controles vulneráveis demonstram a consequência da restauração insegura e validam a instrumentação; os comparadores completos/retomados e com/sem deduplicação cumprem outra função, de avaliação dos custos e efeitos.

A seção já compara escopos e deve preservar essa precisão. Uma matriz de comparação com antecedentes pode ajudar, desde que seja baseada em leitura e contenha apenas informações verificadas. Não marcar como ausente no antecedente um cenário apenas porque ele não aparece no resumo.

O registro local informa que a descrição de Catoni foi conferida no resumo institucional e na versão curta dos autores; a leitura da versão publicada completa permanece pendente. Fechar essa leitura é prioritário antes de sustentar uma lacuna científica.

### 3.3. Antecipar a distinção entre os controles de estado e o TLS nativo — pp. 1–2 e 9

A modelagem explica corretamente que o checkpoint TLS conserva o contexto de retomada e que a conexão realiza nova derivação. Essa distinção pode aparecer antes, para evitar a interpretação de que serializar uma sessão retomável TLS equivale a salvar sua chave de tráfego e seu contador de registros.

Frase candidata para a introdução, ajustando o espaço disponível:

> O protótipo examina os efeitos de restaurar chaves e contadores, enquanto o piloto TLS avalia a retomada a partir de sessões salvas e sua interação com a aplicação.

Isso separa as evidências sem alongar o modelo de ameaça nem sugerir uma vulnerabilidade demonstrada no OpenSSL.

### 3.4. Preservar o alcance das afirmações sobre PQC e latência

O piloto utiliza criptografia pós-quântica real na configuração descrita. Entretanto, a dependência do contexto de retomada e a deduplicação não são propriedades exclusivas de PQC. O texto deve continuar caracterizando esta configuração, sem atribuir todo o benefício à migração pós-quântica.

O comparador TLS clássico equivalente permanece trabalho futuro, como a conclusão já informa. Ele se torna necessário se a alegação pretendida passar a ser o efeito específico da migração criptográfica. Do mesmo modo, cinco blocos sustentam o relato descritivo apresentado; uma alegação geral de melhora de latência exigiria ampliar e analisar a amostra com essa finalidade.

## 4. Coerência dos resultados

| Medida | Resultado publicado | Leitura adequada |
|---|---|---|
| Protótipo, sem falha | 9.263 → 3.136 bytes; 66,14% | Comparação interna ao protocolo experimental |
| Protótipo, checkpoint truncado | 18.526 → 12.399 bytes; 33,07% | Custo das tentativas no cenário específico |
| Protótipo, segredo de retomada perdido | 9.263 → 9.568 bytes; +3,29% | A tentativa de retomada pode acrescentar custo |
| TLS, handshake com contexto disponível | 23.859 → 2.873 bytes; 87,96% | Fronteira até retorno de SSL_connect |
| TLS, sequência completa, deduplicação ativa | Reduções entre medianas de 55,43% a 55,57% | Tráfego IPv4 observado durante o ensaio |
| Aplicação no piloto TLS | 30 efeitos duplicados no controle; zero com supressão | Efeitos no banco com histórico preservado |

As reduções entre as medianas de tráfego IPv4 são coerentes com o CSV:

| Perda por direção | Completo (bytes) | Retomada (bytes) | Redução |
|---|---:|---:|---:|
| 0% | 157.895 | 70.250 | 55,51% |
| 1% | 157.895 | 70.158 | 55,57% |
| 5% | 158.287 | 70.550 | 55,43% |

São razões entre medianas de cada modo, não medianas de reduções pareadas ou intervalos de confiança. A redação atual faz essa distinção.

Em 1% de perda, as medianas de recuperação no host foram de 482,0 ms no modo completo e 506,8 ms na retomada. O artigo reconhece corretamente que a redução de tráfego não estabelece menor tempo em todas as condições. A conclusão mantém seu foco em comunicação, em vez de prometer uma melhora de tempo não sustentada em todo o piloto.

Também estão preservadas as condições essenciais: credenciais e fontes de entropia fora da restauração do cliente; banco atualizado para deduplicação; identificadores mantidos pelo controlador; ausência de observação direta dos segredos TLS; efeitos restritos ao banco.

## 5. Apresentação e extensão

### Problemas locais observados

1. **Figura 2 invade a seção de relacionados — pp. 6–7.** A Seção 3 começa no fim da p. 6, e a figura da fundamentação aparece no topo da p. 7, interrompendo o parágrafo de abertura dos relacionados. Reposicionar o bloco e conferir a transição; uma barreira localizada é uma possibilidade, desde que não recrie espaços vazios excessivos.
2. **Conclusão com poucas linhas no fim da página — pp. 16–17.** O título e duas linhas de texto ficam separados do restante. Ajustar o texto ou reservar espaço para o início da seção, após a compactação.
3. **Gráficos de resultados ainda coloridos — pp. 12–16.** As Figuras 1–3 seguem a preferência por preto e branco, mas as Figuras 4–7 mantêm azul, verde e laranja. Reexportar os gráficos a partir dos dados, combinando cinza, preenchimentos, linhas e marcadores; conferir a leitura no tamanho final.
4. **Figura 3 grande — p. 10.** O fluxo é legível e não tem sobreposições, mas ocupa bastante altura. Há espaço para reduzir distâncias internas preservando o tamanho das letras.
5. **Continuações com legenda repetida.** As Figuras 4 e 6 têm as duas partes na mesma página. Não há erro de numeração. Após a compactação, avaliar se a organização pode reduzir a repetição de legendas sem transformar cada figura em um bloco que cause novamente grandes vazios.

### Extensão

A nova versão tem 18 páginas, contra 14 do artigo aprovado e 17 da versão anterior revisada. A introdução começa na p. 1, a fundamentação na p. 3, os relacionados na p. 6, a proposta na p. 8, os resultados na p. 11 e a conclusão na p. 16. Referências ocupam parte das pp. 17–18.

A maior extensão merece compactação, mas esses números não demonstram violação do limite de uma chamada. Conferir a edição pretendida antes de definir uma meta obrigatória de páginas.

A compactação deve preservar as fronteiras de medição e as condições das alegações. Priorizar descrições repetidas dos três estados, explicações do fluxo já mostradas na figura, legendas extensas e comentários repetidos sobre os limites do piloto. A organização em seis seções pode ser mantida integralmente.

### Reprodutibilidade

A Tabela 2 melhorou a apresentação da configuração. Ainda faltam no PDF CPU/RAM/SO, versão do Mininet-WiFi e parâmetros relevantes de banda/MTU. Completar a partir dos registros da execução, sem apresentar a máquina atual como se fosse necessariamente a máquina histórica do ensaio.

O link de artefatos exibido e seu destino clicável apontam corretamente para o repositório de PQC-IoT. Registrar também uma versão imutável dos fontes e os manifestos correspondentes tornaria a referência aos experimentos mais precisa.

## 6. Ordem prática para finalizar

1. Alinhar abstract e resumo à medição da sequência completa, mantendo o percentual do handshake com seu escopo.
2. Fechar a leitura do antecedente próximo e formular o diferencial experimental apoiado nessa comparação.
3. Antecipar a distinção entre restauração de chave/contador no protótipo e retomada TLS nativa.
4. Compactar texto e diagramas, mantendo as seis seções e as condições experimentais essenciais.
5. Reexportar gráficos em preto e branco e rever Figura 2, começo da conclusão e continuações.
6. Completar os metadados reprodutíveis e verificar as exigências da chamada pretendida.

O artigo está mais coerente e preciso que a versão anterior. A estrutura do trabalho aprovado foi preservada; a pendência central para a submissão é consolidar o diferencial científico e concluir o acabamento editorial.
