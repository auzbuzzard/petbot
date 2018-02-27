import json, re, urllib3
from enum import Enum

from capabilities.boorus import datastruct

class Result(datastruct.Result):
    pass


class SearchQuery(datastruct.SearchQuery):

    class Order(Enum):
        creation_date = "created_at"
        score = "score"
        wilson_score = "wilson"
        relevance = "relevance"
        width = "width"
        height = "height"
        comments = "comments"
        random = "random"

    def __init__(self, tags: list, args: dict = {}):
        datastruct.SearchQuery.__init__(self, tags, args)

        self.order = args['order'] if 'order' in args else SearchQuery.Order.random
        self.is_desc_order = args['sort'] if 'sort' in args else True

        self.root_url = "https://derpibooru.org"

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

    def request(self):
        print(self.params())
        return self.http.request('GET',
                                 self.root_url + '/search.json',
                                 fields=self.params())


def image(json_dict):
    search_result = Result(json_dict)
    try:
        image_result = Result(search_result.search[0])
        return image_result, int(search_result.total)
    except:
        return None, 0


def utterance(msg, image_result):
    result, count = image_result
    if result is not None and count > 0:
        return (
            "Found image for: {} (from {} results) \n".format(msg, count) +
            "https:{}".format(result.representations['large'])
        )
    else:
        return "Can't find images for: {}. :<".format(msg)


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


if __name__ == '__main__':
    args, tags = parse_args("--e human")

    query = SearchQuery(tags, args)

    r = query.request()

    json_dict = json.loads(r.data.decode('utf-8'))

    image_result = image(json_dict)

    print(utterance(tags, image_result))





