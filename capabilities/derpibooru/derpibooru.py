import certifi, urllib3
import json, re
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

    def __init__(self,
                 tags: list,
                 args: dict = {},
                 order: Order = Order.random, desc: bool = True):
        self.tags = tags
        self.args = args
        self.order = args['order'] if 'order' in args else order
        self.is_desc_order = desc
        self.is_explicit = args['explicit'] if 'explicit' in args else False

        self.filters = {
            'everything': '56027',
            'steady': '150237',
            'default': '100073'
        }

    def params(self):
        params = {
            'q': ",".join(self.tags),
            'sf': self.order.value,
            'sd': 'desc' if self.is_desc_order else 'asc',
            'filter_id': self.filters['steady'] if self.is_explicit else self.filters['default']
        }

        return params


def search(args: dict, tags: list):
    query = SearchQuery(tags, args)
    r = http.request('GET',
                     root_url + 'search.json',
                     fields=query.params())

    json_dict = json.loads(r.data.decode('utf-8'))

    search_result = Result(json_dict)
    try:
        image = Result(search_result.search[0])
        return image, int(search_result.total)
    except:
        return None, 0


def parse_args(message: str):
    pattern = r'--([\w:]+)'
    args_list = re.findall(pattern, message)
    args = {}

    if any(i in ['e'] for i in args_list):
        args['explicit'] = True
    if any(i in ['sort_new'] for i in args_list):
        args['order'] = SearchQuery.Order.creation_date
    if any(i in ['sort_relevance', 'sort_rel'] for i in args_list):
        args['order'] = SearchQuery.Order.relevance
    if any(i in ['sort_score'] for i in args_list):
        args['order'] = SearchQuery.Order.score
    if any(i in ['sort_wscore'] for i in args_list):
        args['order'] = SearchQuery.Order.wilson_score
    if any(i in ['sort_comments'] for i in args_list):
        args['order'] = SearchQuery.Order.comments

    message = re.sub(pattern, '', message)

    return args, [s.strip() for s in message.split(',')]


if __name__ == "__main__":
    search("safe, rainbow dash")







