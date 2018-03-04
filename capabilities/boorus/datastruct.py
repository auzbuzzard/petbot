import certifi, urllib3
import json, random


class Result:
    def __init__(self, data: dict):
        for k, v in data.items():
            setattr(self, k, v)


class SearchQuery:
    http = urllib3.PoolManager(
        10,
        headers={'user-agent': 'Mozilla/5.0 (Windows NT 6.3; rv:36.0) Gecko/20100101 Firefox/36.0'},
        cert_reqs='CERT_REQUIRED',
        ca_certs=certifi.where()
    )

    root_url = "/"

    def __init__(self,
                 tags: list,
                 args: dict = {}):
        self.tags = tags
        self.args = args
        self.is_explicit = args['explicit'] if 'explicit' in args else False

    def params(self) -> dict:
        params = {}

        return params

    def url(self) -> str:
        return self.root_url

    def request(self):
        return self.http.request('GET',
                                 self.root_url + 'search.json',
                                 fields=self.params())


def result_greeter(has_image: bool, is_explicit: bool) -> str:
    try:
        with open('capabilities/boorus/utterances.json') as f:
            utterances = json.load(f)
            utterances = utterances['image_result_greeter']
            utterances = utterances['success'] if has_image else utterances['no_image']
            sentences = utterances['universal']
            if has_image:
                sentences += utterances['explicit'] if is_explicit else utterances['safe']
            return random.choice(sentences)

    except EnvironmentError as e:
        print(e)
        return "I have found this image."
