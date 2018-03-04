import re
import json
import math
import urllib.parse
from enum import Enum
from typing import Optional, Tuple

import discord

from capabilities.boorus import datastruct


class ImageResult(datastruct.Result):
    class Rating(Enum):
        safe = 's'
        questionable = 'q'
        explicit = 'e'

    def __init__(self, data: dict):
        datastruct.Result.__init__(self, data)
        self.rating_enum = self.__rating()
        self.is_explicit = self.rating_enum is not ImageResult.Rating.safe

    def __rating(self) -> Optional[Rating]:
        try:
            return ImageResult.Rating(self.rating)
        except ValueError:
            return None


class SearchQuery(datastruct.SearchQuery):
    def __init__(self, tags: list, args: dict):
        datastruct.SearchQuery.__init__(self, tags, args)

    @staticmethod
    def root_url(is_explicit: bool) -> str:
        return "https://e621.net/" if is_explicit else "https://e926.net/"

    @staticmethod
    def site_name(is_explicit: bool) -> str:
        return 'e621' if is_explicit else 'e926'

    def params(self) -> dict:
        self.tags.append("order:random")
        return {
            'tags': ' '.join(self.tags),
            'limit': 1
        }

    def url(self) -> str:
        return SearchQuery.root_url(self.args['explicit']) + \
               'post/index.json?tags=' + \
               urllib.parse.quote(' '.join(self.tags))

    def request(self):
        return self.http.request('GET',
                                 SearchQuery.root_url(self.args['explicit']) + 'post/index.json',
                                 fields=self.params())


def image(json_dict) -> Optional[ImageResult]:
    return ImageResult(json_dict[0]) if len(json_dict) > 0 else None


def utterance(query: SearchQuery, image_result: Optional[ImageResult], ctx) \
        -> Tuple[str, Optional[discord.Embed]]:
    if image_result is not None:
        return (
            datastruct.result_greeter(
                has_image=True,
                is_explicit=image_result.is_explicit
            ).format(author=ctx.message.author),
            __generate_embed(query=query, image_result=image_result)
        )
    else:
        return datastruct.result_greeter(has_image=False, is_explicit=False).format(tags=query.tags), None


def __generate_embed(query: SearchQuery, image_result: ImageResult) -> discord.Embed:
    markdown_query_tags = __split_tags(query.tags, limit=256)
    embed = discord.Embed(
        title=
        'results: {tags}'
        .format(tags=', '.join(markdown_query_tags[0]) if len(markdown_query_tags) == 1 else
                ', '.join(markdown_query_tags[0][:-1] + '…')),
        description=
        "score: {score:d} | faves: {faves:d} || source: [{site_name}]({root_url}post/show/{id}) || filetype: {filetype}"
        .format(id=image_result.id,
                score=image_result.score,
                faves=image_result.fav_count,
                filetype=image_result.file_ext,
                root_url=SearchQuery.root_url(image_result.is_explicit),
                site_name=SearchQuery.site_name(image_result.is_explicit)),
        url=query.url(),
        color=(65280 if image_result.rating_enum is ImageResult.Rating.safe else  # green
               16776960 if image_result.rating_enum is ImageResult.Rating.questionable else  # yellow
               16711680 if image_result.rating_enum is ImageResult.Rating.explicit else 0)  # red, black
    )

    embed.set_image(url=image_result.sample_url)
    embed.set_author(name=SearchQuery.site_name(image_result.is_explicit),
                     url=SearchQuery.root_url(image_result.is_explicit),
                     icon_url="https://e621.net/favicon-32x32.png")

    return embed


def __split_tags(tags: list, limit=1024) -> list:
    tags_str = ', '.join(tags)
    split = math.ceil(len(tags_str) / limit)
    s_length = int(math.floor(len(tags) / split))
    return [tags[i:i + s_length] for i in range(0, len(tags), s_length)]


def parse_args(message: str):
    pattern = r'--([\w:]+)'
    args_list = re.findall(pattern, message)
    args = {
        'explicit': False
    }

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




