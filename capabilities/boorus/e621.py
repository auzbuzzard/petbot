import re
import json
import math
import urllib.parse
from enum import Enum
from typing import Optional, Tuple, Union

import discord
from discord.ext import commands

from capabilities.boorus import datastruct, errors


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

    def url(self, json: bool=False) -> str:
        return SearchQuery.root_url(self.args['explicit']) + \
               'post/index{json}?tags='.format(json='.json' if json else '') + \
               urllib.parse.quote(' '.join(self.tags))

    def request(self):
        return self.http.request('GET',
                                 SearchQuery.root_url(self.args['explicit']) + 'post/index.json',
                                 fields=self.params())


def image(json_dict: dict) -> Optional[ImageResult]:
    if not json_dict.get('success', False):
        raise errors.SiteFailureStatusError(
            site_message=json_dict.get('reason', ''),
            print_message="uwu I couldn't do that. {}".format(
                "e621 says: {}".format(json_dict['reason']) if 'reason' in json_dict else
                "e621 is saying something in computers that I do not understand ;~;"),
            need_code_block=False
        )
    return ImageResult(json_dict[0]) if len(json_dict) > 0 else None


def utterance(query: SearchQuery,
              image_result: Optional[ImageResult],
              ctx: commands.Context) -> Tuple[str, Optional[Union[discord.Embed, str]]]:
    if image_result is not None:
        return (
            datastruct.result_greeter(
                has_image=True,
                is_explicit=image_result.is_explicit,
                author=ctx.message.author
            ),
            _generate_embed(query=query, image_result=image_result)
        )
    else:
        return datastruct.result_greeter(
            has_image=False,
            is_explicit=query.args['explicit'],
            author=ctx.message.author
        ).format(
            tags=query.tags
        ), None


def _generate_embed(query: SearchQuery, image_result: ImageResult) -> Union[discord.Embed, str]:
    markdown_query_tags = _split_tags(query.tags, limit=256)

    if image_result.file_ext == 'webm':
        return (
                'results: {tags}\n'
                .format(tags=', '.join(markdown_query_tags[0]) if len(markdown_query_tags) == 1 else
                        ', '.join(markdown_query_tags[0][:-1] + '…')) +
                "score: {score:d} | faves: {faves:d} | source: {root_url}post/show/{id}) | filetype: {filetype}\n"
                .format(id=image_result.id,
                        score=image_result.score,
                        faves=image_result.fav_count,
                        root_url=SearchQuery.root_url(image_result.is_explicit),
                        filetype=image_result.file_ext) +
                image_result.file_url
        )

    embed = discord.Embed(
        title=
        'results: {tags}'
        .format(tags=', '.join(markdown_query_tags[0]) if len(markdown_query_tags) == 1 else
                ', '.join(markdown_query_tags[0][:-1] + '…')),
        description=
        "score: {score:d} | faves: {faves:d} | source: [{site_name}]({root_url}post/show/{id}) | filetype: {filetype}"
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


def _split_tags(tags: list, limit=1024) -> list:
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




