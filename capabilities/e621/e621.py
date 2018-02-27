import certifi, urllib3
import json, re
from enum import Enum

http = urllib3.PoolManager(
    cert_reqs='CERT_REQUIRED',
    ca_certs=certifi.where()
)


def root_url(is_explicit: bool):
    return "https://e621.net" if is_explicit else "https://e926.net"


class Result:
    def __init__(self, data: dict):
        for k, v in data.items():
            setattr(self, k, v)


class SearchQuery:

    def __init__(self,
                 tags: list,
                 args: dict = {}):
        self.tags = tags
        self.args = args
        self.is_explicit = args['explicit'] if 'explicit' in args else False

    def params(self):
        params = {
            'q': ",".join(self.tags),
            'sf': self.order.value,
            'sd': 'desc' if self.is_desc_order else 'asc'
        }

        return params


def search(args: dict, tags: list):
    query = SearchQuery(tags, args)
    r = http.request('GET',
                     root_url(query.is_explicit) + '/post/index.json',
                     fields=query.params())

    json_dict = json.loads(r.data.decode('utf-8'))

    search_result = Result(json_dict)
    image = Result(search_result[0]) if len(search_result) > 0 else None

    return image


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

    message = re.sub(pattern, '', message)

    return args, [s.strip() for s in message.split(',')]


if __name__ == "__main__":
    search("safe, rainbow dash")







