import certifi, urllib3
import json
from enum import Enum

from capabilities.derpibooru import result

http = urllib3.PoolManager(
    cert_reqs='CERT_REQUIRED',
    ca_certs=certifi.where()
)

root_url = "https://derpibooru.org/"


class Result:
    def __init__(self, data: dict):
        for k, v in data.items():
            setattr(self, k, v)


class SearchQuery:

    class Order(Enum):
        creation_date = "created_at"
        score = "score"
        wilson_score = "wilson"
        relevance = "relevance"
        width = "width"
        height = "height"
        comments = "comments"
        random = "random"

    def __init__(self, tags: list, order: Order = Order.random, desc: bool = True):
        self.tags = tags
        self.order = order
        self.is_desc_order = desc

    def params(self):

        return {
            'q': ",".join(self.tags),
            'sf': self.order.value,
            'sd': 'desc' if self.is_desc_order else 'asc'
        }


def search(tags: str):
    tags = [s.strip() for s in tags.split(',')]

    query = SearchQuery(tags)
    r = http.request('GET',
                     root_url + 'search.json',
                     fields=query.params())

    json_dict = json.loads(r.data.decode('utf-8'))

    search_result = Result(json_dict)
    image = Result(search_result.search[0])

    return image


if __name__ == "__main__":
    search("safe, rainbow dash")







