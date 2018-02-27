import certifi, urllib3


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

    def __init__(self,
                 tags: list,
                 args: dict = {}):
        self.tags = tags
        self.args = args
        self.is_explicit = args['explicit'] if 'explicit' in args else False

        self.root_url = ""

    def params(self):
        params = {}

        return params

    def request(self):
        return self.http.request('GET',
                                 self.root_url + '/search.json',
                                 fields=self.params())