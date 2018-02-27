import json
from enum import Enum

from capabilities.boorus import derpibooru, e621


class Sites(Enum):
    derpibooru = 1
    e621 = 2


def search(site: Sites, messages: str):
    if site == Sites.derpibooru:
        provider = derpibooru
    elif site == Sites.e621:
        provider = e621

    args, tags = provider.parse_args(messages)

    query = provider.SearchQuery(tags, args)

    r = query.request()

    json_dict = json.loads(r.data.decode('utf-8'))

    image_result = provider.image(json_dict)

    return provider.utterance(tags, image_result)
