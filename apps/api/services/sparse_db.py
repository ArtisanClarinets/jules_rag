from opensearchpy import OpenSearch
from apps.api.core.config import settings

client = OpenSearch(
    hosts=[{'host': settings.OPENSEARCH_HOST, 'port': settings.OPENSEARCH_PORT}],
    http_auth=('admin', settings.OPENSEARCH_PASSWORD),
    use_ssl=True,
    verify_certs=False,
    ssl_show_warn=False
)

def ensure_index(index_name: str):
    if not client.indices.exists(index=index_name):
        client.indices.create(index=index_name, body={
            "settings": {
                "analysis": {
                    "analyzer": {
                        "default": {
                            "type": "standard" # Can be tuned for code
                        }
                    }
                }
            }
        })

def index_document(index_name: str, doc_id: str, body: dict):
    client.index(index=index_name, id=doc_id, body=body)

def search_sparse(index_name: str, query: str, limit: int = 10):
    response = client.search(index=index_name, body={
        "query": {
            "match": {
                "text": query
            }
        },
        "size": limit
    })
    return response['hits']['hits']
