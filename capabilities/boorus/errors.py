from capabilities.boorus import datastruct, booru

class Error(Exception):
    pass


class SiteFailureStatusError(Error):
    def __init__(self, site_message: str, print_message: str, need_code_block: bool):
        self.site_message = site_message
        self.print_message = print_message
        self.need_code_block = need_code_block