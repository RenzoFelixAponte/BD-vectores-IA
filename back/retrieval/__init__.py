"""Subsistema de recuperacion por contenido (Proyecto 2).

Dos modalidades, una misma idea: construir un indice invertido y rankear por
similitud.

- text/   : indice invertido para TEXTO (SPIMI en memoria secundaria + coseno TF-IDF).
- media/  : indice invertido para DESCRIPTORES LOCALES (Bag of Visual/Acoustic Words
            + KNN secuencial e indexado sobre histogramas).

Conexion con el motor SQL:
  parser  -> ast_nodes.TextSearchNode (@@) / ast_nodes.MediaSearchNode (<->)
          -> executor._exec_text_search / executor._exec_media_search
          -> text/text_retriever.TextRetriever / media/media_retriever.MediaRetriever

Todo el nucleo algoritmico (tokenizacion, SPIMI, coseno, codebook, histogramas y
KNN) se implementa a mano, sin librerias de recuperacion. Las librerias externas
solo se usan para EXTRAER descriptores crudos (imagen/audio), no para indexar ni
rankear.
"""
