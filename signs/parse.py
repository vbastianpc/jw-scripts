# -*- coding: utf-8 -*-

import os
import json
import threading
import io
from subprocess import run
import shlex
from PIL import Image

from os.path import join as pj
from io import UnsupportedOperation
from json.decoder import JSONDecodeError

from signs.constants import (
    probe_markers, parse_markers_nwt, parse_markers_raw, ext, woext,
    parse_num_book, attrib_hidden, ffprobe_signature,
    get_nwt_video_info, add_numeration, ffprobe_height, run_progress_bar
)

class JWSigns:
    """
    Clase
    """
    nwt = True
    book = '0'
    chapter = '0'
    input = ''
    work_dir = '.'
    hwaccel = False
    hevc = False
    raw = False

    def __init__(self):
        pass

    def _get_db(self):
        dir = pj(self.work_dir, 'db')
        os.makedirs(dir, exist_ok=True)
        attrib_hidden(dir)
        self.dirdb = pj(dir, 'db.json')
        if not os.path.exists(self.dirdb):
            self.db = {}
        else:
            with open(self.dirdb, 'r', encoding='utf-8') as json_file:
                try:
                    self.db = json.load(json_file)
                except (UnsupportedOperation, JSONDecodeError):
                    self.db = {}

    def get_match_videos(self):
        print(f'Getting nwt videos from {self.input}', end='\t-> ', flush=True)
        if os.path.isfile(self.input):
            return [self.input]
        elif os.path.isdir(self.input):
            videos = []
            for dirpath, dirnames, filenames in os.walk(self.input):
                for filename in sorted(filenames):
                    if filename.startswith('nwt') and (filename.endswith('.mp4') or filename.endswith('.m4v')):

                        book = int(get_nwt_video_info(filename, 'booknum'))
                        chapter = int(get_nwt_video_info(filename, 'chapter'))

                        if (book in self.books or 0 in self.books) and (chapter in self.chapters or 0 in self.chapters):
                            videos.append(pj(dirpath, filename))
                break

        print(f'{len(videos)} found')
        if len(videos) == 0:
            print('No nwt videos found')
            exit(1)
        return videos


    def get_cutup_verses(self):
        print(f'Getting verses videos from {self.work_dir}', end='\t-> ', flush=True)
        path = pj(self.work_dir, 'db', 'ready.json')
        try:
            with open(path, 'r', encoding='utf-8') as jsonfile:
                self.ready = json.load(jsonfile)

        except (FileNotFoundError, UnsupportedOperation, JSONDecodeError):
            self.ready = {}

        versiculos = {}
        for dirpath, dirnames, filenames in os.walk(self.work_dir):
            if dirpath[len(self.work_dir):].count(os.sep) < 2: # nivel prinicpal y un nivel de subdirectorio
                for filename in sorted(filenames):
                    if (filename.endswith('.mp4') or filename.endswith('.m4v')) and not filename.startswith('nwt'):
                        if self.ready.get(woext(filename)) == os.stat(pj(dirpath, filename)).st_size:
                            versiculos.update({woext(filename): pj(dirpath, filename)})
                            # print(f'...fast...{filename}')
                        elif 'vbastianpc' in ffprobe_signature(pj(dirpath, filename)):
                            versiculos.update({woext(filename): pj(dirpath, filename)})
                            self.ready.update({woext(filename): os.stat(pj(dirpath, filename)).st_size})
                        # print(f'...slow...{filename}')

        with open(path, 'w', encoding='utf-8') as jsonfile:
            json.dump(self.ready, jsonfile, ensure_ascii=False, indent=4)
        print(f'{len(versiculos)} found')
        return versiculos


    def raw_parse(self):
        """Parsing any video"""
        self._get_db()
        result = []
        match_videos = self.get_match_videos()
        verse_videos = self.get_cutup_verses()
        for video in match_videos:
            json_markers = probe_markers(video)
            markers = parse_markers_raw(json_markers, video)

            for mark in markers:
                # print(mark['title'], end='\t')
                print(verse_videos.get(mark['title']), mark['title'])
                if self.db.get(woext(video)) == os.stat(video).st_size and \
                        verse_videos.get(mark['title']):
                    pass
                else:
                    result.append(mark)
            self.db[woext(video)] = os.stat(video).st_size
        self.write_json(self.db)
        print('raw', verse_videos)
        return result

    def parse(self):
        """Parsing nwt videos"""
        self.work_dir = expandpath(self.work_dir)
        self.input = expandpath(self.input)
        self.books = [int(bk) for bk in self.book.split(',')]
        self.chapters = [int(chp) for chp in self.chapter.split(',')]

        self._get_db()
        print('This may take several minutes', flush=True)
        verse_videos = self.get_cutup_verses()
        match_videos = self.get_match_videos()
        self.num_bookname = parse_num_book(get_nwt_video_info(match_videos[0], 'lang'))
        add_numeration(self.work_dir, self.num_bookname)
        print(f'Getting chapter marks from {self.input}', end='\t-> ')
        result = []
        for video in match_videos:
            booknum = get_nwt_video_info(video, 'booknum')
            json_markers = probe_markers(video)
            markers = parse_markers_nwt(json_markers,
                                        video,
                                        bookname=self.num_bookname[booknum])
            for mark in markers:
                # print(mark['title'], end='\t')
                if self.db.get(woext(video)) == os.stat(video).st_size and \
                        verse_videos.get(mark['title']):
                    # verse it exist and is the latest version. do nothing
                    pass
                    # print('already exists')
                else:
                    result.append(mark)
            self.db[woext(video)] = os.stat(video).st_size
        self.write_json(self.db)
        print(f'{len(result)} found\n')
        return result

    def cook(self, result):
        if not result:
            print('Everything is ok. There is no work to do.')
            return
        print('Splitting videos...')
        total = len(result)
        format_spec = f'0{len(str(total))}'
        for i, task in enumerate(result, start=1):
            print(f'[{format(i, format_spec)}/{total}]\t', task['title'], end='\t-->\t', flush=True)
            if self.raw is True:
                color = False
                outvid = pj(self.work_dir,
                            f"{format(i, '02')} {task['title']}{ext(task['parent'])}")
            else:
                outdir = pj(self.work_dir, task['booknum'] + ' ' + self.num_bookname[task['booknum']])
                name = task['title']
                color = self._verificaBordes(task['parent'], task['start'])

            self.finished_event = threading.Event()
            progress_bar_thread = threading.Thread(target=run_progress_bar, args=(self.finished_event,))
            progress_bar_thread.start()
            process = self.split_video(
                input=task['parent'],
                start=task['start'],
                end=task['end'],
                outdir=outdir,
                name=name,
                color=color,
                hwaccel=self.hwaccel,
                hevc=self.hevc,
                )
            self.finished_event.set()
            progress_bar_thread.join()
            if process.returncode == 0:
                print('done')
                self.ready.update({name: os.stat(pj(outdir, name + '.mp4')).st_size})

        path = pj(self.work_dir, 'db', 'ready.json')
        with open(path, 'w', encoding='utf-8') as jsonfile:
            json.dump(self.ready, jsonfile, ensure_ascii=False, indent=4)

    def split_video(self, input, start, end, outdir, name, color=None, hwaccel=False, hevc=False):
        os.makedirs(outdir, exist_ok=True)
        bareoutput = pj(outdir, name)
        prelude = f'ffmpeg -y -loglevel warning -hide_banner -ss {str(start)} '
        decodeHW = '-hwaccel cuda '
            # cmd += ['-hwaccel', 'cuvid', '-c:v', 'h264_cuvid']
        core = (
            f'-i "{input}" -to {str(end - start)} -map_chapters -1 '
            f'-metadata title="{name}" -metadata genre=vbastianpc '
            '-metadata comment=https://github.com/vbastianpc/jw-scripts '
        )
        if color:
            height = self.current_height
            delta = int(height * 4 / 3 * 0.02)  # 2% security
            width_bar = int((height * 16 / 9 - height * 4 / 3) / 2) + delta
            x_offset = int(height * 16 / 9 - width_bar)
            core += ('-vf '
                f'"drawbox=x=0:y=0:w={width_bar}:h={height}:color={color[0]}:t=fill, '
                f'drawbox=x={x_offset}:y=0:w={width_bar}:h={height}:color={color[1]}:t=fill" '
                )
        if hevc:
            encodeHW = '-c:v hevc_nvenc -cq:v 31 -profile:v high '
            encodeCPU = '-c:v libx265 '
        else:
            encodeHW = '-c:v h264_nvenc -cq:v 26 -profile:v high '
            encodeCPU = '-c:v libx264 '
        end = f'-f mp4 \"{bareoutput + ".part"}\" '

        if hwaccel:
            cmd = prelude + decodeHW + core + encodeHW + end
        else:
            cmd = prelude + core + encodeCPU + end

        # https://superuser.com/questions/1320389/updating-mp4-chapter-times-and-names-with-ffmpeg

        console = run(shlex.split(cmd), capture_output=True)

        if console.returncode == 0: # success
            try:
                os.remove(bareoutput + '.mp4')
            except FileNotFoundError:
                pass
            finally:
                os.rename(bareoutput + '.part', bareoutput + '.mp4')
        else: # error
            try:
                os.remove(bareoutput + '.part')
            except FileNotFoundError:
                pass

            err = console.stderr.decode('utf-8')
            print(err)
            if self.hwaccel and 'CUDA' in err:
                print('It seems that your graphics card is not compatible'
                      ', or you must install the drivers and CUDA Toolkit. '
                      '\nPlease visit https://github.com/vbastianpc/jw-scripts/wiki/jw-signs-(E)')
                exit(1)
        return console

    def _verificaBordes(self, dir_file, start):
        cmd = f'ffmpeg -y -hide_banner -ss {str(start + 0.5)} -i {dir_file} -vframes 1 -f image2pipe -'
        console = run(shlex.split(cmd), capture_output=True)
        try:
            img = Image.open(io.BytesIO(console.stdout))
        except:
            return None
        else:
            self.current_height = ffprobe_height(dir_file)
            rgb = img.getpixel((20, 20))

            if rgb == (0, 0, 0):
                delta = int(self.current_height * 4 / 3 * 0.03)  # 3% safe bandwith
                x = int((self.current_height * 16 / 9 - self.current_height * 4 / 3) / 2) + delta
                y = int(self.current_height / 2)
                r, g, b = img.getpixel((x, y))
                colorleft = format(r, '02X') + format(g, '02X') + format(b, '02X')

                x = int(self.current_height * 16 / 9) - x
                r, g, b = img.getpixel((x, y))
                colorright = format(r, '02X') + format(g, '02X') + format(b, '02X')
                color = (colorleft, colorright)
            else:
                color = False
            return color

    def write_json(self, data):
        with open(self.dirdb, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)


def expandpath(path):
    path = os.path.abspath(os.path.expanduser(os.path.expandvars(path)))
    if os.path.isfile(path) or os.path.isdir(path):
        return path
    else:
        raise ValueError(f'{path} is not a valid directory')
