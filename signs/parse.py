# -*- coding: utf-8 -*-

import os
import json
import threading
import io
from subprocess import run
from os.path import join as pj
from io import UnsupportedOperation
from json.decoder import JSONDecodeError

from signs.constants import (
    FFMPEG, probe_markers, parse_markers_nwt, parse_markers_raw, ext, woext,
    parse_num_book, attrib_hidden,
    get_nwt_video_info, add_numeration, ffprobe_height, run_progress_bar
)


try:
    from PIL import Image
except ModuleNotFoundError:
    print('Installing Pillow package')
    p = run(['pip', 'install', 'Pillow'], capture_output=True)
    if p.returncode == 0:
        from PIL import Image
    else:
        print(
            'No se ha podido instalar la librería PIL. Debes instalarla '
            'manualmente.\n\nSi estás en Windows, abre el Símbolo del sistema '
            'como administrador y ejecuta: pip install PIL\n\nSi estás en '
            'macOS o Linux, abre el terminal y escribe: '
            'sudo pip install PIL')
        exit()


class JWSigns:
    """
    Clase
    """
    nwt = None
    book = 0
    input = ''
    work_dir = '.'
    hwaccel = False
    raw = False

    def __init__(self):
        pass

    def _get_db(self):
        dir = pj(self.work_dir, 'db')
        os.makedirs(dir, exist_ok=True)
        attrib_hidden(dir)
        self.dirdb = pj(dir, 'db.json')
        if not os.path.exists(self.dirdb):
            with open(self.dirdb, 'w', encoding='utf-8'):
                pass
            db = {}
        else:
            with open(self.dirdb, 'r', encoding='utf-8') as json_file:
                try:
                    db = json.load(json_file)
                except (UnsupportedOperation, JSONDecodeError):
                    db = {}
        return db

    def get_match_videos(self):
        if os.path.isfile(self.input):
            return [self.input]
        elif os.path.isdir(self.input):
            videos = []
            for dirpath, dirnames, filenames in os.walk(self.input):
                for filename in sorted(filenames):
                    if filename.endswith('.mp4') or filename.endswith('.m4v'):

                        if self.nwt is None:
                            self.nwt = True if filename.startswith('nwt') else False
                        if self.nwt is True and filename.startswith('nwt'):
                            book = int(get_nwt_video_info(filename, 'booknum'))
                            if book == self.book or self.book == 0:
                                videos.append(pj(dirpath, filename))

                        elif self.nwt is False and not filename.startswith('nwt'):
                            videos.append(pj(dirpath, filename))

            return videos
        else:
            raise ValueError(f'{self.input} is not a valid directory')

    def get_cutup_verses(self):
        versiculos = {}
        for dirpath, dirnames, filenames in os.walk(self.work_dir):
            for filename in filenames:
                if filename.endswith('.mp4') or filename.endswith('.m4v') \
                        and not filename.startswith('nwt'):
                    versiculos.setdefault(woext(filename),
                                          pj(dirpath, filename))
        return versiculos


    def raw_parse(self):
        """Parsing any video"""
        self.db = self._get_db()
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
        self.db = self._get_db()
        print(f'Getting splited videos from {self.work_dir}... ', end='')
        verse_videos = self.get_cutup_verses()
        print(f'done\nGetting match videos from {self.input}... ', end='')
        match_videos = self.get_match_videos()
        print('done')

        self.num_bookname = parse_num_book(get_nwt_video_info(match_videos[0], 'lang'))
        add_numeration(self.work_dir, self.num_bookname)
        print('Getting chapter marks from match videos... ', end='')
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
                    # verse it exist, do nothing
                    pass
                    # print('already exists')
                else:
                    result.append(mark)
            self.db[woext(video)] = os.stat(video).st_size
        self.write_json(self.db)
        print('done\n')
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
                color = self._verificaBordes(task['parent'], task['start'])
                outvid = pj(self.work_dir,
                            task['booknum'] + ' ' + self.num_bookname[task['booknum']],
                            task['title'] + ext(task['parent']))

            self.finished_event = threading.Event()
            progress_bar_thread = threading.Thread(target=run_progress_bar, args=(self.finished_event,))
            progress_bar_thread.start()
            process = self.split_video(
                input=task['parent'],
                start=task['start'],
                end=task['end'],
                output=outvid,
                color=color,
                hwaccel=self.hwaccel,
                )
            self.finished_event.set()
            progress_bar_thread.join()
            if process.returncode == 0:
                print('done')

    # TODO verificar borde de acuerdo a tamaño de video. Al igual que vf franjas de color
    def split_video(self, input, start, end, output, color=None, hwaccel=False):
        os.makedirs(os.path.dirname(output), exist_ok=True)
        cmd = [FFMPEG, '-y', '-loglevel', 'warning',
               '-hide_banner', '-ss', str(start)]
        if hwaccel:
            cmd += ['-hwaccel', 'cuvid', '-c:v', 'h264_cuvid']
        cmd += ['-i', input, '-to', str(end - start),
                '-map_chapters', '-1', '-metadata', 'title=',
                '-metadata', 'comment=Created by vbastianpc\n\nhttps://github.com/vbastianpc']
        if color:
            height = self.current_height
            delta = int(height * 4 / 3 * 0.02)  # 2% security
            width_bar = int((height * 16 / 9 - height * 4 / 3) / 2) + delta
            x_offset = int(height * 16 / 9 - width_bar)
            vf = (
                f'drawbox=x=0:y=0:w={width_bar}:h={height}:color={color[0]}:t=fill, '
                f'drawbox=x={x_offset}:y=0:w={width_bar}:h={height}:color={color[1]}:t=fill'
                )
            # print(vf)
            cmd += ['-vf', vf]
        if hwaccel and not color:
            cmd += ['-c:v', 'h264_nvenc', '-preset', 'slow', '-b:v', '1000k']
        cmd += ['-f', 'mp4', output + '.part']

        # print(' '.join(cmd))
        # https://superuser.com/questions/1320389/updating-mp4-chapter-times-and-names-with-ffmpeg
        console = run(cmd, capture_output=True)
        if console.returncode == 0:
            try:
                os.remove(output)
            except FileNotFoundError:
                pass
            os.rename(output + '.part', output)

        else:
            try:
                os.remove(output + '.part')
            except FileNotFoundError:
                pass

            err = console.stderr.decode('utf-8')
            print(err)
            if self.hwaccel and 'cuvid' in err:
                print('It seems that your graphics card is not compatible'
                      ', or you must install the drivers and CUDA Toolkit. '
                      '\nPlease visit https://github.com/vbastianpc/'
                      'jw-scripts/wiki/jw-signs-(E)')
                exit(1)

        return console

    def _verificaBordes(self, dir_file, start):
        cmd = [FFMPEG, '-y', '-hide_banner', '-ss', str(start + 0.5),
               '-i', dir_file, '-vframes', '1', '-f', 'image2pipe', '-']
        console = run(cmd, capture_output=True)
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
