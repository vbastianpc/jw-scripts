from sys import platform
from sys import stderr
import os
import time
import re
import subprocess
import shutil

import json
import hashlib
import urllib.request
import urllib.parse

from signs.constants import woext, ext


if platform.startswith('win'):
    import ctypes
    kernel32 = ctypes.windll.kernel32
    kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)


def msg(s):
    print(s, file=stderr, flush=True)


class JWBroadcasting:
    """
    Class for parsing and downloading videos from JW Broadcasting

    Tweak the variables, and run :method:`parse` and then :method:`download_all`
    """
    __mindate = None
    lang = 'S'
    quality = 720
    subtitles = False
    burned_subtitles = False
    streaming = False
    quiet = 0
    checksums = False
    title = False
    index_category = 'VideoOnDemand'
    rate_limit = '1M'
    curl_path = 'curl'
    keep_free = 0
    exclude_category = ''
    # Used if streaming is True
    utc_offset = 0

    def __init__(self):
        # Will populated with Media objects by parse()
        self.result = []
        # Used by download_media()
        self._checked_files = set()

    @property
    def lang(self):
        """Language code

        If the code is None, print out a list and exit. If code is invalid, raise ValueError.
        """
        return self.__lang

    @lang.setter
    def lang(self, code):
        url = 'https://data.jw-api.org/mediator/v1/languages/E/web?clientType=tvjworg'

        with urllib.request.urlopen(url) as response:
            response = json.loads(response.read().decode())

            if not code:
                # Print table of language codes
                msg('language codes:')
                for lang in sorted(response['languages'], key=lambda x: x['name']):
                    msg('{:>3}  {:<}'.format(lang['code'], lang['name']))
                exit()
            else:
                # Check if the code is valid
                for lang in response['languages']:
                    if lang['code'] == code:
                        self.__lang = code
                        return
                msg('language codes:')
                for lang in sorted(response['languages'], key=lambda x: x['name']):
                    msg('{:>3}  {:<}'.format(lang['code'], lang['name']))
                print(code + ': invalid language code')
                exit()

    @property
    def mindate(self):
        """Minimum date of media

        Set to 'YYYY-MM-DD'. It will be stored as seconds since epoch.
        """
        return self.__mindate

    @mindate.setter
    def mindate(self, date):
        try:
            self.__mindate = time.mktime(time.strptime(date, '%Y-%m-%d'))
        except ValueError:
            raise ValueError('wrong date format')

    def parse(self):
        """Index JW Broadcasting categories recursively

        :return: A list containing Category and Media objects
        """
        if self.streaming:
            section = 'schedules'
        else:
            section = 'categories'

        # Load the queue with the requested (keynames of) categories
        queue = self.index_category.split(',')
        exclude = self.exclude_category.split(',')
        for key in queue:
            if key in exclude:
                continue
            url = 'https://data.jw-api.org/mediator/v1/{s}/{L}/{c}?detailed=1&clientType=tvjworg&utcOffset={o}'
            url = url.format(s=section, L=self.lang, c=key, o=self.utc_offset)

            with urllib.request.urlopen(url) as response:
                response = json.loads(response.read().decode())

                if 'status' in response and response['status'] == '404':
                    raise ValueError('No such category or language')

                # Add new category to the result, or re-use old one
                cat = Category()
                self.result.append(cat)
                cat.key = response['category']['key']
                cat.name = response['category']['name']
                cat.home = cat.key in self.index_category.split(',')

                if self.quiet < 1:
                    msg('{} ({})'.format(cat.key, cat.name))

                if self.streaming:
                    # Save starting position
                    if 'position' in response['category']:
                        cat.position = response['category']['position']['time']

                else:
                    if 'subcategories' in response['category']:
                        for subcat in response['category']['subcategories']:
                            # Add subcategory to current category
                            s = Category()
                            s.key = subcat['key']
                            s.name = subcat['name']
                            cat.add(s)
                            # Add subcategory to queue for parsing later
                            if s.key not in queue:
                                queue.append(s.key)

                if 'media' in response['category']:
                    for media in response['category']['media']:
                        # Skip videos marked as hidden
                        if 'tags' in response['category']['media']:
                            if 'WebExclude' in response['category']['media']['tags']:
                                continue

                        if 'type' in media and media['type'] == 'audio':
                            # Simply pick first audio stream for the time being...
                            mediafile = media['files'][0]
                        else:
                            mediafile = self._get_best_video(media['files'])

                        m = Media()
                        m.name = media['title']
                        if self.subtitles:
                            subs = self._get_subs(media['files'])
                            if 'url' in subs:
                                m.url = subs['url']
                            else:
                                continue
                            if 'checksum' in subs:
                                m.md5 = subs['checksum']
                        else:
                            m.url = mediafile['progressiveDownloadURL']
                            if 'checksum' in mediafile:
                                m.md5 = mediafile['checksum']
                            if 'filesize' in mediafile:
                                m.size = mediafile['filesize']

                        # Save time data (not needed when streaming)
                        if 'firstPublished' in media and not self.streaming:
                            # Remove last stuff from date, what is it anyways?
                            d = re.sub('\.[0-9]+Z$', '', media['firstPublished'])
                            # Try to convert it to seconds
                            try:
                                d = time.mktime(time.strptime(d, '%Y-%m-%dT%H:%M:%S'))
                            except ValueError:
                                pass
                            else:
                                m.date = d
                                if self.mindate and d < self.mindate:
                                    continue

                        cat.add(m)

        return self.result

    def _get_subs(self, video_list: list):
        for video in video_list:
            if 'subtitles' in video:
                return video['subtitles']
        return {}

    def _get_best_video(self, video_list: list):
        """Take a list of media files and metadata and return the best one"""

        videos = []
        for vid in video_list:
            try:
                # Convert labels like 720p to int in a most forgiving way
                vid['label'] = int(vid['label'][:-1])
            except ValueError or TypeError:
                # In case the label is wrong format, use frame height
                # (But this may be misleading)
                vid['label'] = vid['frameHeight']
            # Only save videos that match quality setting
            if vid['label'] <= self.quality:
                videos.append(vid)

        # Sort by quality and subtitle setting
        videos = sorted(videos, reverse=True, key=lambda v: v['label'])
        videos = sorted(videos, reverse=True, key=lambda v: v['subtitled'] == self.burned_subtitles)
        best_video = videos[0]
        return best_video

    def download_media(self, media, directory, check_only=False):
        """Download media file and check it.

        Download file, check MD5 sum and size, delete file if it missmatches.

        :param media: a Media instance
        :param directory: dir to save the files to
        :param check_only: bool, True means no downloading
        :return: filename, or None if unsuccessful
        """
        if not os.path.exists(directory) and not self.download:
            return None

        os.makedirs(directory, exist_ok=True)

        base = urllib.parse.urlparse(media.url).path
        if self.title:
            file_extension = os.path.splitext(os.path.basename(base))[-1]
            title = media.name.replace('"', "'").replace(':', '.')
            base = ''.join(c if c.isalnum() or c in ".-_()¡!¿';, " else '' \
                           for c in title \
                           ) + file_extension
        else:
            base = os.path.basename(base)

        # Delete files if same basename in main dir
        if self.type == 'video':
            for path, dirnames, filenames in os.walk(directory):
                for filename in filenames:
                    if filename == base:
                        pass
                    elif woext(filename) == woext(base):
                        os.remove(os.path.join(path, filename))
                        print('deleted:', os.path.join(path, filename))
                break
        file = os.path.join(directory, base)
        # Only try resuming and downloading once
        resumed = False
        downloaded = False
        progressbar = False if self.subtitles else True
        while True:

            if os.path.exists(file): # os.path.exists(file):

                # Set timestamp to date of publishing
                # NOTE: Do this before checking _checked_files since
                # this is not done for newly renamed .part files!
                if media.date:
                    os.utime(file, (media.date, media.date))

                if os.path.getsize(file) == media.size or not media.size:
                    # File size is OK or unknown - Validate checksum
                    if self.checksums and media.md5 and _md5(file) != media.md5:
                        # Checksum is bad - Remove
                        if self.quiet < 2:
                            msg('checksum mismatch, deleting: {}'.format(base))
                        os.remove(file)
                    else:
                        # Checksum is correct
                        return file
                else:
                    # File size is bad - Delete
                    msg('size mismatch, deleting: {}'.format(base))
                    os.remove(file)

            elif check_only:
                # The rest of this method is only applicable in download mode

                return None

            elif os.path.exists(file + '.part'):

                fsize = os.path.getsize(file + '.part')

                if fsize == media.size or not media.size:
                    # File size is OK - Validate checksum
                    if self.checksums and media.md5 and _md5(file + '.part') != media.md5:
                        # Checksum is bad - Remove
                        if self.quiet < 2:
                            msg('checksum mismatch, deleting: {}'.format(base + '.part'))
                        os.remove(file + '.part')
                    else:
                        # Checksum is correct or unknown - Move and approve
                        os.rename(file + '.part', file)
                        return file
                elif fsize < media.size and not resumed:
                    # File is smaller - Resume download once
                    resumed = True
                    if self.quiet < 2:
                        msg('resuming: {} ({})'.format(base + '.part', media.name))
                    _curl(media.url,
                          file + '.part',
                          resume=True,
                          rate_limit=self.rate_limit,
                          curl_path=self.curl_path,
                          progress=progressbar,
                          )
                else:
                    # File size is bad - Remove
                    msg('size mismatch, deleting: {}'.format(base + '.part'))
                    os.remove(file + '.part')

            else:
                # Download whole file once
                if not downloaded:
                    msg('downloading: {} ({})'.format(base, media.name))
                    _curl(media.url,
                          file + '.part',
                          rate_limit=self.rate_limit,
                          curl_path=self.curl_path,
                          progress=progressbar,
                          )
                    downloaded = True
                else:
                    # If we get here, all tests have failed.
                    # Resume and regular download too.
                    # There is nothing left to do.
                    msg('failed to download: {} ({})'.format(base, media.name))
                    return None


    def prepare_download(self, wd=None):
        """Check media files

        :param wd: directory where files will be saved
        """
        if wd is None:
            wd = self.work_dir

        exclude = self.exclude_category.split(',')
        media_list = [x for cat in self.result
                      if cat.key not in exclude or cat.home
                      for x in cat.content
                      if not x.iscategory]
        media_list = sorted(media_list, key=lambda x: x.date or 0, reverse=True)

        # Trim down the list of files that need to be downloaded
        download_list = []
        checked_files = []
        no_download_list = []
        for media in media_list:
            if not media.url:
                continue
            # Only run this check once per filename
            path = urllib.parse.urlparse(media.url).path
            base = os.path.basename(path)
            if base in checked_files:
                continue
            checked_files.append(base)

            # Skip previously deleted files
            f = urllib.parse.urlparse(media.url).path
            f = os.path.basename(f)
            f = os.path.join(wd, f + '.deleted')
            if os.path.exists(f):
                continue

            # Search for local media and delete broken files
            media.file = self.download_media(media, wd, check_only=True)

            if not media.file:
                download_list.append(media)
            else:
                no_download_list.append(media)

        self.download_list = download_list
        self.checked_files = checked_files
        self.no_download_list = no_download_list
        return download_list


    def manage_downloads(self, wd=None, download_list=None):

        if download_list is None:
            download_list = self.download_list
        if wd is None:
            wd = self.work_dir

        for media in download_list:
            # Clean up until there is enough space
            # print(media.name, media.size, media.file, media.url, sep=' | ')
            space = shutil.disk_usage(wd).free
            needed = media.size + self.keep_free if media.size else 0
            if space < needed:
                s = 'Please, free up hard disk space\n' \
                    'Free space: {:} MiB, needed: {:} MiB'.format(space//1024**2, needed//1024**2)
                raise Exception(s)
            # Download the video
            if self.download:
                print('[{}/{}]'.format(download_list.index(media) + 1, len(download_list)), end=' ', file=stderr)
                media.file = self.download_media(media, wd)


class JWPubMedia(JWBroadcasting):
    type = 'video'
    book = 0
    # Disable rate limit completely
    rate_limit = '0'
    curl_path = 'curl'
    quality = 720
    lang = 'S'

    def parse(self):
        """Index JW org sound recordings

        :return: a list containing Category and Media objects
        """
        url_template = 'https://pubmedia.jw-api.org/GETPUBMEDIALINKS' \
                       '?output=json&alllangs={a}&langwritten={L}&txtCMSLang={L}&pub={p}'
        rawpub = self.pub
        # Watchtower/Awake reference is split up into pub and issue
        magazine_match = re.match('(wp?|g)([0-9]+)', self.pub)
        if magazine_match:
            url_template += '&issue={i}'
            self.pub = magazine_match.group(1)
            queue = [magazine_match.group(2)]
        else:
            url_template += '&booknum={i}'
            queue = [self.book]

        # Check language code
        # This must be done after the magazine stuff
        # We want the languages for THAT publication only, or else the list gets SOO long
        # The language is checked on the first pub in the queue
        url = url_template.format(L='E', p=self.pub, i=queue[0], a='1')

        with urllib.request.urlopen(url) as response:
            response = json.loads(response.read().decode())

            # Check if the code is valid
            if self.lang not in response['languages']:
                msg('language codes:')
                for lang in sorted(response['languages'], key=lambda x: response['languages'][x]['name']):
                    msg('{:>3}  {:<}'.format(lang, response['languages'][lang]['name']))
                raise ValueError(self.lang + ': invalid language code')
        print('Getting url...')
        bare = True
        for key in queue:
            url = url_template.format(L=self.lang, p=self.pub, i=key, a=0)
            # print('URL:', url)
            book = Category()
            self.result.append(book)

            if self.pub == 'bi12' or self.pub == 'nwt':
                book.key = format(int(key), '02')
                # This is the starting point if the value in the queue
                # is the same as the one the user specified
                book.home = key == self.book
            else:
                book.key = self.pub
                book.home = True
            try:
                with urllib.request.urlopen(url) as response:
                    response = json.loads(response.read().decode())
                    book.name = response['pubName']

                    if self.quiet < 1:
                        msg('{} {}'.format(book.key, book.name))

                    # For the Bible's index page
                    # Add all books to the queue
                    if key == 0 and (self.pub == 'bi12' or self.pub == 'nwt'):
                        for i in range(1, 67):
                            queue.append(i)

                    for fileformat in response['files'][self.lang]:
                        for chptr in response['files'][self.lang][fileformat]:
                            if self.type == 'video' and \
                                    int(chptr['label'][:-1]) != self.quality:
                                # not match quality
                                continue
                            # match mimetype
                            if chptr['mimetype'].startswith(self.type) or \
                                    chptr['mimetype'].endswith(self.type):
                                m = Media()
                                m.url = chptr['file']['url']
                                m.name = chptr['title'].replace('&nbsp;', ' ')
                                m.md5 = chptr['file']['checksum']
                                if 'filesize' in chptr:
                                    m.size = chptr['filesize']

                                book.add(m)
                                bare = False

            except urllib.error.HTTPError:
                pass
        if bare:
            s = (f'It seems that there are no {self.type} files in {self.lang} '
                 f'language for {rawpub} publication')
            if self.type == 'video':
                s += f' in quality {self.quality}'
            msg(s)
            msg(f'Check this URL: {url}')
        else:
            print('...done\n')
        return self.result


def _md5(file):
    """Return MD5 of a file."""
    hash_md5 = hashlib.md5()
    with open(file, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def _curl(url, file, resume=False, rate_limit='0', curl_path='curl', progress=False):
    """Throttled file download by calling the curl command."""
    if curl_path:
        proc = [curl_path, url, '-o', file]

        if rate_limit != '0':
            proc.append('--limit-rate')
            proc.append(rate_limit)
        if progress:
            proc.append('--progress-bar')
        else:
            proc.append('--silent')
        if resume:
            # Download what is missing at the end of the file
            proc.append('--continue-at')
            proc.append('-')

        subprocess.call(proc, stderr=stderr)
        print('\033[F\033[K', end='', flush=True)

    else:
        # If there is no rate limit, use urllib (for compatibility)
        request = urllib.request.Request(url)
        file_mode = 'wb'

        if resume:
            # Ask server to skip the first N bytes
            request.add_header('Range', 'bytes={}-'.format(os.stat(file).st_size))
            # Append data to file, instead of overwriting
            file_mode = 'ab'

        response = urllib.request.urlopen(request)

        # Write out 1MB at a time, so whole file is not lost if interrupted
        with open(file, file_mode, encoding='utf-8') as f:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)


class Category:
    """Object to put category info in."""
    iscategory = True
    key = None
    name = None
    # Whether or not this is a "starting point"
    home = False
    # Used for streaming
    position = 0

    def __init__(self):
        self.content = []

    def add(self, obj):
        """Add an object to :var:`self.content`

        :param obj: an instance of :class:`Category` for :class:`Media`
        """
        self.content.append(obj)


class Media:
    """Object to put media info in."""
    iscategory = False
    url = None
    name = None
    md5 = None
    date = None
    size = None
    file = None
