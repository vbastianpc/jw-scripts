# -*- coding: utf-8 -*-

import os
import itertools
import re
import json
import platform
import ctypes
from subprocess import run
from os.path import join as pj
import urllib.request
import urllib.parse
from sys import stderr


def msg(s):
    print(s, file=stderr, flush=True)


def run_progress_bar(finished_event):
    chars = itertools.cycle(r'-\|/')
    while not finished_event.is_set():
        print('\b' + next(chars), end='', flush=True)
        finished_event.wait(0.2)
    print('\b ', end='')

def parse_num_book(lang):
    dir_file = pj(
        os.path.dirname(os.path.realpath(__file__)),
        'languages',
        f'lang-{lang}.json')
    if os.path.exists(dir_file):
        with open(dir_file, 'r', encoding='utf-8') as json_file:
            return json.load(json_file)
    else:
        url_template = 'https://pubmedia.jw-api.org/GETPUBMEDIALINKS' \
                       '?output=json&alllangs=0&langwritten={L}&txtCMSLang={L}' \
                       '&pub=nwt&booknum={i}'
        num_book = {}
        print(f'Getting booknum and bookname in {lang} language')
        for i in range(1, 67):
            url = url_template.format(L=lang, i=i)
            with urllib.request.urlopen(url) as response:
                response = json.loads(response.read().decode())
                # Check if the code is valid
                if lang not in response['languages']:
                    msg('language codes:')
                    for language in sorted(response['languages'], key=lambda x: response['languages'][x]['name']):
                        msg('{:>3}  {:<}'.format(language, response['languages'][language]['name']))
                    raise ValueError(lang + ': invalid language code')
                    exit()
                num_book.setdefault(format(i, '02'), response['pubName'])
                print(format(i, '02'), response['pubName'])
        os.makedirs(os.path.dirname(dir_file), exist_ok=True)
        with open(dir_file, 'w', encoding='utf-8') as json_file:
            json.dump(num_book, json_file, ensure_ascii=False, indent=4)
        return num_book


def attrib_hidden(dir):
    if platform.system() == 'Windows':
        ctypes.windll.kernel32.SetFileAttributesW(dir, 0x02)
    elif platform.system() == 'Darwin':
        run(['chflags', 'hidden', dir], capture_output=True)


def ext(filename):
    return os.path.splitext(os.path.basename(filename))[-1]


def woext(filename):
    return os.path.splitext(os.path.basename(filename))[0]


def probe_markers(filename):
    """
    Returns markers (chapters) from filename with ffprobe
    """
    console = run(['ffprobe', '-v', 'quiet', '-show_chapters',
                   '-print_format', 'json', filename
                   ],
                  capture_output=True)
    if console.returncode == 0:
        return json.loads(console.stdout.decode('utf-8'))['chapters']
    else:
        print(f'error {filename}')
        return []


def parse_markers_raw(markers, filename):
    result = []
    for data in markers:
        raw_title = data['tags']['title'].rstrip('\r').rstrip()
        title = ''.join([c if c.isalnum() or c in ' .-' else ' ' for c in raw_title]).strip()
        result.append(
            {
                'parent': filename,
                'title': title,
                'start': float(data['start_time']),
                'end': float(data['end_time']),
            }
        )
    return result


def parse_markers_nwt(markers, filename, bookname):
    """
    [
        {
            'parent': filename,
            'title': title,
            'booknum': booknum,
            'start': start,
            'end': end
        },
    ]
    """
    result = []
    for data in markers:
        raw_title = data['tags']['title'].rstrip('\r').rstrip()
        chptr_verse = get_chptr_verse(raw_title)
        if chptr_verse:
            result.append(
                {
                    'parent': filename,
                    'title': f'{bookname} {chptr_verse}',
                    'booknum': get_nwt_video_info(filename, 'booknum'),
                    'start': float(data['start_time']),
                    'end': float(data['end_time']),
                }
            )
        else:
            # No match chpter verse
            pass
    return result


def get_nwt_video_info(filename, info):
    try:
        if info == 'booknum':
            result = os.path.basename(filename).split('_')[1]
        elif info == 'bookalias':
            result = os.path.basename(filename).split('_')[2]
        elif info == 'lang':
            result = os.path.basename(filename).split('_')[3]
        elif info == 'chapter':
            result = os.path.basename(filename).split('_')[4]
    except IndexError:
        return False
    else:
        return result


def get_chptr_verse(raw_title):
    """
        INPUT                     |   OUTPUT
        --------------------------|-----------
        Gén. 1:1                  |   01 01
        Juec. 4:14                |   04 14
        Rut 1:4                   |   01 04
        1 Sam. 1:4                |   01 04
        Cant. de Cant. 2:5        |   02 05
        Inicio                    |   None
        Mateo                     |   None
        Mat. 1:1                  |   01 01
        *Mat. 17:21 Nota          |   None
        * Juan 5:4 Nota           |   None
        * Juan 8:1-11 Nota        |   None
        Hech. 8:37 Nota           |   None
        Luc. 17:36 nota           |   None
        1 Corintios               |   None
    """
    if any(char in raw_title for char in '*#'):
        return
    match = re.search(r'((\d+)?:?\d+)$', raw_title)
    if match:
        try:
            chptr, verse = match.group().split(':')
        except ValueError:
            verse = match.group()
            return format(int(verse), '02')
        else:
            return format(int(chptr), '02') + ' ' + format(int(verse), '02')


def probe_general(video):
    cmd_probe_general = ['ffprobe', '-v', 'quiet', '-show_format',
                         '-print_format', 'json', video]
    console = run(cmd_probe_general, capture_output=True)
    return json.loads(console.stdout.decode('utf-8'))


def ffprobe_signature(video):
    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format_tags=genre',
           '-of', 'default=noprint_wrappers=1:nokey=1', video]
    console = run(cmd, capture_output=True)
    return console.stdout.decode('utf-8').strip()


def ffprobe_height(video):
    cmd = ['ffprobe', '-v', 'quiet', '-show_entries', 'stream=height',  '-of',
           'default=noprint_wrappers=1:nokey=1', '-select_streams', 'v:0',
           video]
    console = run(cmd, capture_output=True)
    height = console.stdout.decode('utf-8')
    try:
        return int(height)
    except ValueError:
        print(height, 'no se pudo')
        pass


def add_numeration(wd, num_bookname):
    for booknum, bookname in num_bookname.items():
        try:
            os.rename(pj(wd, bookname),
                      pj(wd, f'{booknum} {bookname}'))
        except FileNotFoundError:
            pass


def remove_numeration(wd, num_bookname):
    for booknum, bookname in num_bookname.items():
        try:
            os.rename(pj(wd, f'{booknum} {bookname}'),
                      pj(wd, bookname))
        except FileNotFoundError:
            pass


if __name__ == '__main__':
    pass
