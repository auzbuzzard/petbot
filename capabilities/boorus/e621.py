import re, json

from capabilities.boorus import datastruct


class Result(datastruct.Result):
    pass


class SearchQuery(datastruct.SearchQuery):

    def __init__(self,
                 tags: list,
                 args: dict = {}):
        datastruct.SearchQuery.__init__(self, tags, args)

        self.root_url = "https://e621.net" if self.is_explicit else "https://e926.net"

    def params(self):
        self.tags.append("order:random")
        params = {
            'tags': ' '.join(self.tags),
            'limit': 1
        }

        return params

    def request(self):
        return self.http.request('GET',
                                 self.root_url + '/post/index.json',
                                 fields=self.params())


def image(json_dict):
    return Result(json_dict[0]) if len(json_dict) > 0 else None


def utterance(msg, image_result):
    if image_result is not None:
        return (
                "Found image for: {}\n".format(msg) +
                "{}".format(image_result.sample_url)
        )
    else:
        return "Can't find images for: {}. :<".format(msg)


def parse_args(message: str):
    pattern = r'--([\w:]+)'
    args_list = re.findall(pattern, message)
    args = {}

    if any(i in ['e'] for i in args_list):
        args['explicit'] = True

    message = re.sub(pattern, '', message)

    return args, [s.strip() for s in message.split(',')]


if __name__ == '__main__':
    args, tags = parse_args("--e horsecock")

    query = SearchQuery(tags, args)

    r = query.request()

    json_dict = json.loads(r.data.decode('utf-8'))

    image_result = image(json_dict)

    print(utterance(tags, image_result))




