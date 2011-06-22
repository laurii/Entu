from bo import *
from database import *

import urllib


class Search(boRequestHandler):

    def get(self, searchstr = None):

        searchstr = urllib.unquote(searchstr).decode('utf8')[1:]
        d = []
        form = DictionariesForm()

        if searchstr:
            d = Dictionary.all().search(searchstr).fetch(100)

        self.view('dictionary', 'dictionary_search.html', {'dictionaries': d, 'search': searchstr, 'form': form})


def main():
    Route([
            (r'/dictionary/search(.*)', Search),
        ])


if __name__ == '__main__':
    main()