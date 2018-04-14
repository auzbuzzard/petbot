import json, re, math, urllib.parse
from enum import Enum
from typing import Optional, Union, Tuple

import discord
from discord.ext import commands

from capabilities.boorus import datastruct


class ImageResult(datastruct.Result):
    class Rating(Enum):
        safe = 40482
        suggestive = 43502
        questionable = 39068
        explicit = 26707

    def __init__(self, data: dict):
        datastruct.Result.__init__(self, data)
        self.rating = self.__rating()
        self.rating_image = self.__rating_image()

    def __rating(self) -> Optional[Rating]:
        if ImageResult.Rating.safe.value in self.tag_ids:
            return ImageResult.Rating.safe
        elif ImageResult.Rating.suggestive.value in self.tag_ids:
            return ImageResult.Rating.suggestive
        elif ImageResult.Rating.questionable.value in self.tag_ids:
            return ImageResult.Rating.questionable
        elif ImageResult.Rating.explicit.value in self.tag_ids:
            return ImageResult.Rating.explicit
        else:
            return None

    def __rating_image(self) -> Optional[str]:
        if self.rating is ImageResult.Rating.safe:
            return 'https://derpicdn.net/img/2012/9/22/104281/medium.png'
        elif self.rating is ImageResult.Rating.suggestive:
            return 'https://derpicdn.net/img/2013/12/27/507170/medium.png'
        elif self.rating is ImageResult.Rating.questionable:
            return 'https://derpicdn.net/img/2012/7/13/42188/medium.png'
        elif self.rating is ImageResult.Rating.explicit:
            return 'https://derpicdn.net/img/2012/7/13/42206/medium.png'
        else:
            return None


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

    @staticmethod
    def root_url():
        return "https://derpibooru.org/"

    def __init__(self, tags: list, args: dict = {}):
        datastruct.SearchQuery.__init__(self, tags, args)

        self.order = args.get('order', SearchQuery.Order.random)
        self.is_desc_order = args.get('sort', True)

        self.filters = {
            'everything': '56027',
            'steady': '150237',
            'default': '100073'
        }

    def params(self) -> dict:
        params = {
            'q': ",".join(self.tags),
            'sf': self.order.value,
            'sd': 'desc' if self.is_desc_order else 'asc',
            'filter_id':
                self.filters['everything'] if self.args.get('filter') == 'everything' else
                self.filters['steady'] if self.is_explicit else
                self.filters['default']
        }

        return params

    def url(self, json: bool = False) -> str:
        return self.root_url() + \
               'search{json}?q='.format(json='.json' if json else '') + \
               ','.join([str.replace(i, ' ', '+') for i in self.tags])

    def request(self):
        return self.http.request('GET',
                                 self.root_url() + 'search.json',
                                 fields=self.params())


def image(json_dict) -> (Optional[ImageResult], int):
    search_result = datastruct.Result(json_dict)
    try:
        image_result = ImageResult(search_result.search[0])
        return image_result, int(search_result.total)
    except:
        return None, 0


def utterance(query: SearchQuery,
              image_result: (Optional[ImageResult], int),
              ctx: commands.Context) -> Tuple[str, Optional[Union[discord.Embed, str]]]:
    result, count = image_result
    if result is not None and count > 0:
        return (
            datastruct.result_greeter(
                has_image=True,
                is_explicit=result.rating is ImageResult.Rating.explicit,
                author=ctx.message.author
            ),
            _generate_embed(query, count, result)

        )
    else:
        return datastruct.result_greeter(
            has_image=False,
            is_explicit=query.args['explicit'],
            author=ctx.message.author
        ).format(
            tags=query.tags
        ), None


def _generate_embed(query: SearchQuery, count: int,
                    image_result: ImageResult) -> Union[discord.Embed, str]:
    markdown_query_tags = _split_tags(query.tags, limit=256)

    if image_result.original_format == 'webm':
        return (
            '{count} result{s}: {tags}\n'
                .format(count=count, s='s' if count != 1 else '',
                        tags=', '.join(markdown_query_tags[0]) if len(markdown_query_tags) == 1 else
                        ', '.join(markdown_query_tags[0][:-1] + '…')) +
            "score: {score:d} | faves: {faves:d} | source: https://derpibooru.org/{id} | filetype: {filetype}\n"
                .format(id=image_result.id,
                        score=image_result.score,
                        faves=image_result.faves,
                        filetype=image_result.original_format) +
            'https:' + image_result.representations['large']
        )

    embed = discord.Embed(
        title=
        '{count} result{s}: {tags}'
            .format(count=count, s='s' if count != 1 else '',
                    tags=', '.join(markdown_query_tags[0]) if len(markdown_query_tags) == 1 else
                    ', '.join(markdown_query_tags[0][:-1] + '…')),
        description=
        "score: {score:d} | faves: {faves:d} | source: [derpibooru](https://derpibooru.org/{id}) | filetype: {filetype}"
            .format(id=image_result.id,
                    score=image_result.score,
                    faves=image_result.faves,
                    filetype=image_result.original_format),
        url=query.url(json=False),
        color=(65280 if image_result.rating is ImageResult.Rating.safe else  # green
               255 if image_result.rating is ImageResult.Rating.suggestive else  # blue
               16776960 if image_result.rating is ImageResult.Rating.questionable else  # yellow
               16711680 if image_result.rating is ImageResult.Rating.explicit else 0)  # red, black

    )

    embed.set_image(url='https:' + image_result.representations['large'])
    embed.set_author(name="Derpibooru", url="https://derpibooru.org/",
                     icon_url="https://derpicdn.net/img/2017/10/22/1567638/thumb_small.jpeg")

    return embed


def _split_tags(tags: list, limit=1024) -> list:
    tags_str = ', '.join(tags)
    split = math.ceil(len(tags_str) / limit)
    s_length = int(math.floor(len(tags) / split))
    return [tags[i:i + s_length] for i in range(0, len(tags), s_length)]


def parse_args(message: str) -> (dict, list):
    pattern = r'--([\w:]+)'
    args_list = re.findall(pattern, message)
    args = {
        'output_compact': True,
        'order': SearchQuery.Order.random,
        'explicit': False
    }

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
    if any(i in ['full', 'full_output'] for i in args_list):
        args['output_compact'] = False
    if any(i in ['filter_everything', 'f_everything'] for i in args_list):
        args['filter'] = 'everything'

    message = re.sub(pattern, '', message)

    return args, [s.strip() for s in message.split(',')]


if __name__ == '__main__':
    args, tags = parse_args("--e human")

    query = SearchQuery(tags, args)

    r = query.request()

    json_dict = json.loads(r.data.decode('utf-8'))

    image_result = image(json_dict)

    print(utterance(tags, image_result))
