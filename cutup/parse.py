# -*- coding: utf-8 -*-

import os
from os.path import join as pj
import json
from subprocess import run

from io import UnsupportedOperation
from json.decoder import JSONDecodeError

from cutup.constants import (
    FFMPEG, probe_markers, ext, woext, parse_num_book, mkdir_hidden,
    get_nwt_video_info,
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


def agregar_numeracion(wd, num_bookname):
    for booknum, bookname in num_bookname.items():
        try:
            os.rename(pj(wd, bookname),
                      pj(wd, f'{booknum} {bookname}'))
        except FileNotFoundError:
            pass


def quitar_numeracion(wd, num_bookname):
    for booknum, bookname in num_bookname.items():
        try:
            os.rename(pj(wd, f'{booknum} {bookname}'),
                      pj(wd, bookname))
        except FileNotFoundError:
            pass


class JWSigns:
    """
    Clase
    """
    nwt = True
    book = 0
    dirin = None
    file = None
    work_dir = None
    hwaccel = False

    def __init__(self):
        pass

    def _get_db(self):
        print(self.work_dir)
        dir = pj(self.work_dir, 'db')
        print(dir)
        mkdir_hidden(dir)
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
        if self.file:
            return [self.file]
        videos = []
        for dirpath, dirnames, filenames in os.walk(self.dirin):
            for filename in filenames:
                if filename.endswith('.mp4') or filename.endswith('.m4v'):
                    if self.nwt and filename.startswith('nwt'):
                        videos.append(pj(dirpath, filename))
                    elif not self.nwt and not filename.startswith('nwt'):
                        videos.append(pj(dirpath, filename))
        return videos

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
        print(self.db, '\n\n')
        verse_videos = self.get_cutup_verses()
        chapter_videos = self.get_match_videos()
        self.num_bookname = parse_num_book(
            get_nwt_video_info(chapter_videos[0], 'lang'),
            self.work_dir,
            )
        quitar_numeracion(self.work_dir, self.num_bookname)

        result = []
        for video in chapter_videos:
            booknum = get_nwt_video_info(video, 'booknum')
            markers = probe_markers(video, bookname=self.num_bookname[booknum])
            for mark in markers:
                print(mark['title'], end='\t')
                if self.db.get(woext(video)) == os.stat(video).st_size and \
                        verse_videos.get(mark['title']):
                    # verse it exist, do nothing
                    print('already exists')
                else:
                    print('to split')
                    result.append(mark)
            self.db[woext(video)] = os.stat(video).st_size
        return result

    def cook(self, result):
        print('')
        for task in result:
            print(task['title'], end=' --> ')
            color = self._verificaBordes(task['parent'], task['start'])
            outvid = pj(self.work_dir, self.num_bookname[task['booknum']],
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
                print(process.stdout, process.stderr)
        self.write_json(self.db)

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
            vf = (f'drawbox=x=0:y=0:w=170:h=720:color={color}:t=fill, '
                  f'drawbox=x=1110:y=0:w=170:h=720:color={color}:t=fill')
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

        try:
            im = imageio.imread(snapshot)
        except OSError:
            return None
        else:
            rgb = tuple(im[20][20])
            if rgb == (0, 0, 0):
                color = '0x{0[0]:x}{0[1]:x}{0[2]:x}'.format(im[165][360])
            else:
                color = False
            os.remove(snapshot)
            return color

    def write_json(self, data):
        with open(self.dirdb, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
