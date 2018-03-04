import re
import json
from typing import Optional, Union, Tuple

import discord

from capabilities.boorus import datastruct


class ImageResult(datastruct.Result):
    pass


class SearchQuery(datastruct.SearchQuery):

    def __init__(self,
                 tags: list,
                 args: dict = {}):
        datastruct.SearchQuery.__init__(self, tags, args)

    @staticmethod
    def root_url(is_explicit: bool) -> str:
        return "https://e621.net/" if is_explicit else "https://e926.net/"

    def params(self) -> dict:
        self.tags.append("order:random")
        params = {
            'tags': ' '.join(self.tags),
            'limit': 1
        }

        return params

    def url(self) -> str:
        return self.root_url + 'post/index.json?tags=' + ','.join(self.tags)

    def request(self):
        return self.http.request('GET',
                                 self.root_url + 'post/index.json',
                                 fields=self.params())


def image(json_dict) -> Optional[ImageResult]:
    return ImageResult(json_dict[0]) if len(json_dict) > 0 else None


def utterance(query: SearchQuery, image_result: (Optional[ImageResult], int), ctx, embed=False) \
        -> Union[Tuple[str, discord.Embed], str]:
    if image_result is not None:
        return (

        ) if embed else (
                "Found image for: {}\n".format(query.tags) +
                "{}".format(image_result.sample_url)
        )
    else:
        return "Can't find images for: {}. :<".format(query.tags)


def __generate_embed(query: SearchQuery, image_result: ImageResult) -> discord.Embed:
    markdown_query_tags = __generate_tag_markdown(query.tags)
    # print(query.url())
    embed = discord.Embed(
        title='Searching for:',
        description=', '.join(markdown_query_tags[0]),
        url=query.url(),
        color=(65280 if image_result.rating is ImageResult.Rating.safe else  # green
               255 if image_result.rating is ImageResult.Rating.suggestive else  # blue
               16776960 if image_result.rating is ImageResult.Rating.questionable else  # yellow
               16711680 if image_result.rating is ImageResult.Rating.explicit else 0)  # red, black

    )

    embed.set_image(url='https:' + image_result.representations['large'])
    # if image_result.rating is not None:
    #     print('thumb', image_result.rating_image)
    #     embed.set_thumbnail(url=image_result.rating_image)
    embed.set_author(name="Derpibooru", url="https://derpibooru.org/",
                     icon_url="https://derpicdn.net/img/2017/10/22/1567638/thumb_small.jpeg")
    embed.set_footer(text="Image hosted by: derpibooru.org",
                     icon_url="https://derpicdn.net/img/2017/10/22/1567638/thumb_small.jpeg")

    if len(markdown_query_tags) > 1:
        for i in range(1, len(markdown_query_tags)):
            embed.add_field(name="cont'd", value=', '.join(markdown_query_tags[i]), inline=False)

    embed.add_field(name="Score:",
                    value="```py\n{upvotes:d} - {downvotes:d} = {score:d}\n```".format(upvotes=image_result.upvotes,
                                                                                       downvotes=image_result.downvotes,
                                                                                       score=image_result.score),
                    inline=True)
    embed.add_field(name="Faves:", value="```py\n{faves:d}\n```".format(faves=image_result.faves), inline=True)
    embed.add_field(name="Uploaded by:", value="{uploader}".format(uploader=image_result.uploader), inline=False)
    # embed.add_field(name="Description:",
    #                 value=image_result.description[:1024]
    #                 if len(image_result.description) > 1024 else image_result.description,
    #                 inline=True)

    markdown_image_tags = __generate_tag_markdown([v.strip() for v in image_result.tags.split(',')])
    # print(markdown_image_tags)
    for i in range(0, min(len(markdown_image_tags), 4)):
        # print(', '.join(markdown_image_tags[i]))
        embed.add_field(name=("Tags:" if i == 0 else "Tags (cont'd):"),
                        value=', '.join(markdown_image_tags[i]), inline=False)

    embed.add_field(name="Source:",
                    value="[derpibooru](https://derpibooru.org/{id})"
                    .format(id=image_result.id),
                    inline=False)

    # embed.add_field(name="Source:",
    #                 value="[derpibooru](https://derpibooru.org/{id}) | [original]({source_url})"
    #                 .format(id=image_result.id, source_url=image_result.source_url),
    #                 inline=False)

    return embed


def __generate_tag_markdown(tags: list) -> list:
    # print('tags:', tags)
    m_tags = ["[{v}](https://derpibooru.org/search?q={vs})".format(v=v, vs=str.replace(v, ' ', '+')) for v in tags]
    # print('m_tags:', m_tags)
    m_tags_str = ', '.join(m_tags)
    # print(len(m_tags_str), m_tags_str)
    split = math.ceil(len(m_tags_str) / 1024)
    # print('split:', split, len(m_tags_str))
    s_length = int(math.floor(len(m_tags) / split))
    # print(split, s_length)
    return [m_tags[i:i + s_length] for i in range(0, len(m_tags), s_length)]



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




