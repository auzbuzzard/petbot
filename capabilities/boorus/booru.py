import json
from enum import Enum
from typing import Tuple, Optional

import discord

from capabilities.boorus import derpibooru, e621


class Sites(Enum):
    derpibooru = 1
    e621 = 2


def search(site: Sites, ctx, messages: str) -> Tuple[str, Optional[discord.Embed]]:
    if site == Sites.derpibooru:
        provider = derpibooru
    elif site == Sites.e621:
        provider = e621

    args, tags = provider.parse_args(messages)

    query = provider.SearchQuery(tags, args)

    r = query.request()

    json_dict = json.loads(r.data.decode('utf-8'))

    try:
        image_result = provider.image(json_dict)

        if site == Sites.derpibooru:
            return provider.utterance(query=query, image_result=image_result, ctx=ctx, embed=True, compact=args[
                'output_compact'] if 'output_compact' in args else True)
        elif site == Sites.e621:
            return provider.utterance(query=query, image_result=image_result, ctx=ctx)

    except ValueError as e:
        raise e
