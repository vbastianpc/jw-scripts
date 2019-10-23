# -*- coding: utf-8 -*-

import os
from os.path import join as pj
import json
from subprocess import run

from io import UnsupportedOperation
from json.decoder import JSONDecodeError

from cutup.constants import (
    FFMPEG, probe_markers, ext, woext, parse_num_book, attrib_hidden,
    get_nwt_video_info, add_numeration, ffprobe_height
)


try:
    import imageio
except ModuleNotFoundError:
    print('Instalando librería imageio...')
    p = run(['pip', 'install', 'imageio'], capture_output=True)
    if p.returncode == 0:
        import imageio
    else:
        print(
            'No se ha podido instalar la librería imageio. Debes instalarla '
            'manualmente.\n\nSi estás en Windows, abre el Símbolo del sistema '
            'como administrador y ejecuta: pip install imageio\n\nSi estás en '
            'macOS o Linux, abre el terminal y escribe: '
            'sudo pip install imageio')


class JWSigns:
    """
    Clase
    """
    nwt = None
    book = 0
    input = None
    work_dir = None
    hwaccel = False

    def __init__(self):
        pass

    def _get_db(self):
        dir = pj(self.work_dir, 'db')
        os.makedirs(dir, exist_ok=True)
        attrib_hidden(dir)
        self.dirdb = pj(dir, 'db.json')
        if not os.path.exists(self.dirdb):
            with open(self.dirdb, 'w'):
                pass
            db = {}
        else:
            with open(self.dirdb, 'r') as json_file:
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

    def parse(self):
        self.db = self._get_db()
        verse_videos = self.get_cutup_verses()
        match_videos = self.get_match_videos()
        if self.nwt is False:
            print('For now I can only split Bible videos')
            exit()

        self.num_bookname = parse_num_book(
            get_nwt_video_info(match_videos[0], 'lang'),
            self.work_dir,
            )
        add_numeration(self.work_dir, self.num_bookname)

        result = []
        for video in match_videos:
            booknum = get_nwt_video_info(video, 'booknum')
            markers = probe_markers(video, bookname=self.num_bookname[booknum])
            for mark in markers:
                # print(mark['title'], end='\t')
                if self.db.get(woext(video)) == os.stat(video).st_size and \
                        verse_videos.get(mark['title']):
                    # verse it exist, do nothing
                    pass
                    # print('already exists')
                else:
                    # print('to split')
                    result.append(mark)
            self.db[woext(video)] = os.stat(video).st_size
        return result

    def cook(self, result):
        if not result:
            print('Everything is ok. There is no work to do.')
            return
        for task in result:
            print(task['title'], end=' --> ')
            color = self._verificaBordes(task['parent'], task['start'])
            outvid = pj(self.work_dir,
                        task['booknum'] + ' ' + self.num_bookname[task['booknum']],
                        task['title'] + ext(task['parent']))
            process = self.split_video(
                input=task['parent'],
                start=task['start'],
                end=task['end'],
                output=outvid,
                color=color,
                hwaccel=self.hwaccel,
                )
            if process.returncode == 0:
                print('done')
            else:
                print(process.stderr.decode('utf-8'))
                if self.hwaccel:
                    print('It seems that your graphics card is not compatible')
                try:
                    os.remove(outvid)
                except FileNotFoundError:
                    pass
        self.write_json(self.db)

    # TODO verificar borde de acuerdo a tamaño de video. Al igual que vf franjas de color
    def split_video(self, input, start, end, output, color=None, hwaccel=False):
        os.makedirs(os.path.dirname(output), exist_ok=True)
        cmd = [FFMPEG, '-y', '-loglevel', 'warning',
               '-hide_banner', '-ss', str(start)]
        if hwaccel:
            cmd += ['-hwaccel', 'cuvid', '-c:v', 'h264_cuvid']
        cmd += ['-i', input, '-to', str(end - start),
                '-map_chapters', '-1', '-metadata', 'title=',
                '-metadata', 'comment=Created by vbastianpc']
        if color:
            height = self.current_height
            delta = int(height * 4 / 3 * 0.02)  # 2% security
            width_bar = int((height * 16 / 9 - height * 4 / 3) / 2) + delta
            x_offset = int(height * 16 / 9 - width_bar)
            vf = (
                f'drawbox=x=0:y=0:w={width_bar}:h={height}:color={color[0]}:t=fill, '
                f'drawbox=x={x_offset}:y=0:w={width_bar}:h={height}:color={color[1]}:t=fill'
                )
            print(vf)
            cmd += ['-vf', vf]
        if hwaccel:
            cmd += ['-c:v', 'h264_nvenc']
        cmd += [output]

        # print(' '.join(cmd))
        # https://superuser.com/questions/1320389/updating-mp4-chapter-times-and-names-with-ffmpeg
        return run(cmd, capture_output=True)

    def _verificaBordes(self, dir_file, start):
        ruta = os.path.dirname(dir_file)
        snapshot = os.path.join(ruta, dir_file + '.jpg')
        cmd = [FFMPEG,
               '-y', '-hide_banner',
               '-ss', str(start + 0.5),
               '-i', dir_file,
               '-vframes', '1',
               snapshot]
        run(cmd, capture_output=True)
        self.current_height = ffprobe_height(dir_file)
        try:
            im = imageio.imread(snapshot)
        except OSError:
            return None
        else:
            rgb = tuple(im[20][20])
            if rgb == (0, 0, 0):
                delta = int(self.current_height * 4 / 3 * 0.03)  # 3% security
                x = int((self.current_height * 16 / 9 - self.current_height * 4 / 3) / 2) + delta
                y = int(self.current_height / 2)
                r, g, b = im[y][x]
                colorleft = format(r, '02X') + format(g, '02X') + format(b, '02X')

                x = int(self.current_height * 16 / 9) - x
                r, g, b = im[y][x]
                colorright = format(r, '02X') + format(g, '02X') + format(b, '02X')
                color = (colorleft, colorright)
            else:
                color = False
            os.remove(snapshot)
            return color

    def write_json(self, data):
        with open(self.dirdb, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
