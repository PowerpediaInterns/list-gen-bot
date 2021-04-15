# =============================
# IMPORTS
# =============================
import pywikibot    # for making the bot
import requests     # for making requests to the API, in order to generate pages
import re           # for regex methods
import urllib3      # for ignoring the warnings related to making HTTP requests


# =============================
# CONSTANTS: these can be changed by the user as needed
# =============================

# the number of pages this bot will go through before stopping
PAGES_TO_GO_THROUGH = 25

# the title of the page that stores the last page this bot has seen 
# and where to pick up on a later execution
STORAGE_PAGE = "Powerpedia:ListGenBotInfo"

# regex
list_content_start = re.compile(r'\{\{ListGenBot-SourceStart\|(.+)\}\}')
list_content_end = re.compile(r'\{\{ListGenBot-SourceEnd\}\}')

list_render_template = re.compile(r'(\{\{ListGenBot-List(.*)Start\|(.+)\}\})(?:.*\n)+.*(\{\{ListGenBot-List(.*)End\}\})', re.MULTILINE)

title_search = re.compile(r"^(=+)([^=]*)(=+)[ ]?$")

# =============================
# BOT DEFINITION
# =============================

class ListGenBot:
    '''
    A template for other bots.
    '''

    def __init__(self, site: pywikibot.site.APISite, reference_page_title: str):
        '''
        Creates a new bot.
        The bot will run on the given site.
        The bot will store its information on the page with the title given.
        '''
        self.site = site
        self.api_url = site.protocol() + "://" + site.hostname() + site.apipath()
        self.reference_page_title = reference_page_title

    def _get_page(self, page_name: str) -> pywikibot.Page:
        return pywikibot.Page(self.site, page_name)

    def _get_page_text(self, page_name: str) -> [str]:
        '''
        Gets the text for a page. Returns it as a list of lines.
        '''
        page = pywikibot.Page(self.site, page_name)
        page_lines = page.text.split('\n')
        return page_lines

    def _pages_from(self, start_point: str) -> "page generator":
        '''
        Returns a generator with pages starting from the given page.
        The number of pages to run on is based on the constant for this module.
        '''
        # create a new request session 
        my_session = requests.Session()

        # define the necessary restrictions for the search
        api_arguments= {
            "action": "query",
            "format": "json",
            "list": "allpages",
            "apfrom": start_point,
            "aplimit": PAGES_TO_GO_THROUGH
        }

        # make the request, and store it as a json
        request = my_session.get(url=self.api_url, params=api_arguments, verify=False)
        data = request.json()

        # get and return the received page objects as a generator
        pages = data["query"]["allpages"]
        return pages

    def _get_page_start(self) -> str:
        '''
        Returns the page that this bot is supposed to start editing from,
        according to this bot's reference page.
        '''
        page = pywikibot.Page(self.site, self.reference_page_title)
        return page.text.split('\n')[0]

    def _set_page_start(self, new_start: str) -> None:
        '''
        Sets the page that this bot will start from next to the string given.
        '''
        page = pywikibot.Page(self.site, self.reference_page_title)
        page.text = new_start
        page.save("Store new page from last execution.")

    def run(self) -> None:
        '''
        Runs the bot on a certain number of pages.
        Records the last page the bot saw on a certain Mediawiki page.
        '''
        # get the pages to run on
        start_page_title = self._get_page_start()
        last_page_seen = ""
        pages_to_run = self._pages_from(start_page_title)

        # loop through pages
        for page in pages_to_run:
            # run main function
            last_page_seen = page['title']
            self.main_function(last_page_seen)

        # when done, set the page that we need to start from next
        if len(list(pages_to_run)) < PAGES_TO_GO_THROUGH:
            # if we hit the end, then loop back to beginning
            self._set_page_start("")
        else:
            # otherewise, just record the last page seen
            self._set_page_start(last_page_seen)

    def main_function(self, page: str) -> None:
        '''
        Loops through the page.
        Finds areas where content needs to be added to a certain list.
        Adds that content.
        '''
        page_lines = self._get_page_text(page)
        in_list = None
        list_content = []

        # find list content
        for line in page_lines:
            if in_list:
                if self._find_list_content_end(line):
                    # we need to end the list
                    self._add_to_list(
                        content=list_content,
                        section=page,
                        list_name=in_list
                    )
                    in_list = None
                    list_content = []
                elif not self._find_title(line):
                    list_content.append(line)
            else:
                # check if we need to enter a list
                in_list = self._find_list_content_start(line)
        
        # render lists
        page = self._get_page(page)
        new_text = list_render_template.sub(
            repl=self._render_list,
            string=page.text
        )
        page.text = new_text

        if page.text != new_text:
            page.save('Render lists')
    
    def _render_list(self, m: 'regex match object') -> str:
        beginning_text, start, list_name, ending_text, end = m.groups()
        page_name = f'ListGenBot {list_name}'
        page_lines = []

        if start == end:        # if this is not true, we just have an error
            if start == 'Sectioned':
                page_lines = [line if not self._find_title(line) else (f"===([[{line.strip('=')}]])===") \
                    for line in self._get_page_text(page_name)]
            elif start == 'Alphabetical':
                page_lines = self._get_page_text(page_name)
                page_lines = filter((lambda x: not self._find_title(x)), page_lines)
                page_lines = sorted(page_lines)
            
        list_text = '\n'.join(page_lines)
        total_text = f'{beginning_text}\n{list_text}\n{ending_text}'
        return total_text

    def _find_list_render_start(self, line: str) -> (str, str) or None:
        '''
        Finds a template indicating the start of
        a list to be rendered.
        If it is, it returns the type of rendering and the name of the list.
        None otherwise.
        '''
        res = list_render_start.search(line)
        return res.group(1), res.group(2) if (res is not None) else None

    def _find_list_render_end(self, line: str) -> str or None:
        '''
        Finds a template indicating the end of a list to
        be rendered.
        Returns the type of the list if found,
        None otherwise.
        '''
        res = list_content_end.search(line)
        return res.group(1)

    def _find_list_content_start(self, line: str) -> str or None:
        '''
        Finds a template indicating the start of content
        to be added to a list.
        If it is, it returns the name of the list.
        None otherwise.
        '''
        res = list_content_start.search(line)
        return res.group(1) if (res is not None) else None

    def _find_list_content_end(self, line: str) -> bool:
        '''
        Finds a template indicating the end of content
        to be added to a list.
        Returns True if the given line is such a template.
        False otherwise.
        '''
        res = list_content_end.search(line)
        return res is not None

    def _find_title(self, line: str) -> bool:
        '''
        Returns True if the given line is a title,
        False otherwise.
        '''
        res = title_search.search(line)
        return res is not None

    def _add_to_list(self, content: [str], section: str, list_name: str) -> None:
        '''
        Adds the given content to the list of name given.
        '''
        # the section is converted to a header
        section = f'=={section}=='
        # the page name refers to the ListGenBot page for the appopriate list
        page_name = f'ListGenBot {list_name}'
        page_lines = self._get_page_text(page_name)

        # step 1: remove the content that was previously in the section 
        start, end = None, None
        for line_no, line in enumerate(page_lines):
            if line == section:
                # the section we are looking for starts here
                start = line_no
            elif start and self._find_title(line):
                # we hit a new section, so stop here
                end = line_no - 1
                break

        if start is not None and end is not None:
            del page_lines[start:end + 1]
        elif end is None:
            del page_lines[start:]

        # step 2: add new content
        if content:
            page_lines.append(section)
            page_lines += content

        # turn the list back into text
        page = self._get_page(page_name)
        page.text = '\n'.join(page_lines)
        page.save('Add list content to list')










# =============================
# SCRIPT
# =============================

if __name__ == "__main__":
    # ignore warning due to making HTTP request (rather than HTTPS)
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # create the bot
    bot = ListGenBot(
        site=pywikibot.Site(),
        reference_page_title=STORAGE_PAGE
    )

    # run the bot
    bot.run()
