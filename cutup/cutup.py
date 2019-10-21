# -*- coding: utf-8 -*-

import os
import time
import string
import ctypes
import platform
import subprocess
from urllib import request
from multiprocessing import Pool
from urllib.error import URLError
from socket import timeout as timeout_error

from cutup.constants import (
    FFMPEG, LIBRO_NUMERO, NUMERO_LIBRO, URL_FILE, DESCARGAS, CORTES,
    probe_marcadores)

try:
    from tinydb import TinyDB, Query
except ModuleNotFoundError:
    print('Instalando librería tinydb...')
    p = subprocess.run(['pip', 'install', 'tinydb'], capture_output=True)
    if p.returncode == 0:
        from tinydb import TinyDB, Query
    else:
        print(
            'No se ha podido instalar la librería tinydb. Debes instalarla '
            'manualmente.\n\nSi estás en Windows, abre el Símbolo del sistema '
            'como administrador y ejecuta: pip install tinydb\n\nSi estás en '
            'macOS o Linux, abre el terminal y escribe: '
            'sudo pip install tinydb')

try:
    import imageio
except ModuleNotFoundError:
    print('Instalando librería imageio...')
    p = subprocess.run(['pip', 'install', 'imageio'], capture_output=True)
    if p.returncode == 0:
        import imageio
    else:
        print(
            'No se ha podido instalar la librería imageio. Debes instalarla '
            'manualmente.\n\nSi estás en Windows, abre el Símbolo del sistema '
            'como administrador y ejecuta: pip install imageio\n\nSi estás en '
            'macOS o Linux, abre el terminal y escribe: '
            'sudo pip install imageio')


Q = Query()



def get_book_name(filename):
    return NUMERO_LIBRO[get_book_index(filename)]


def ext(filename):
    return os.path.splitext(os.path.basename(filename))[-1]


def woext(filename):
    return os.path.splitext(os.path.basename(filename))[0]


class JWSigns:
    '''
    '''
    book = 0

    def __init__(self):
        self.dbd = TinyDB(os.path.join(dbdir_desc, 'dbd.json'))

        self.urls = self.get_urls_from_file()
        self.versiculos = self.get_versiculos_cortados()

    def crea_carpeta(self, carpeta):
        try:
            os.makedirs(carpeta)
        except FileExistsError:
            pass

    def crea_carpeta_oculta(self, carpeta):
        self.crea_carpeta(carpeta)
        if platform.system() == 'Windows':
            ctypes.windll.kernel32.SetFileAttributesW(carpeta, 0x02)
        elif platform.system() == 'Darwin':
            subprocess.run(['chflags', 'hidden', carpeta], capture_output=True)

    def agregar_numeracion(self):
        for book, index in LIBRO_NUMERO.items():
            try:
                os.rename(os.path.join(CORTES, book),
                          os.path.join(CORTES, f'{index}_{book}'))
            except FileNotFoundError:
                pass

    def quitar_numeracion(self):
        for book, index in LIBRO_NUMERO.items():
            try:
                os.rename(os.path.join(CORTES, f'{index}_{book}'),
                          os.path.join(CORTES, book))
            except FileNotFoundError:
                pass

    def is_numeracion(self):
        for dirpath, dirnames, filenames in os.walk(CORTES):
            break
        carpetas_libro = 0
        con_numeracion = 0
        sin_numeracion = 0
        for dirname in dirnames:
            if any(book in dirname for book in LIBRO_NUMERO.keys()):
                carpetas_libro += 1
                try:
                    LIBRO_NUMERO[dirname]
                except KeyError:
                    # hay almenos una carpeta que no tiene numeracion
                    con_numeracion += 1
                else:
                    sin_numeracion += 1
        if carpetas_libro == con_numeracion:
            return True
        elif carpetas_libro == sin_numeracion:
            return False
        else:
            return None  # indeterminado

    def actualiza_biblos(self):
        link = ('https://drive.google.com/uc?export=download&id=1fOYKgpijoZOTq'
                '-VRyGIlR3npq60-Rs_')
        d = request.urlopen(link)
        request.urlretrieve(link, 'biblos.py')
        print("Programa 'biblos' actualizado con fecha", d.info()['Date'])
        print('Cierra esta ventana y abre nuevamente el programa')
        return

    def actualiza_url(self):
        link = ('https://drive.google.com/uc?export=download&id=1DeTwT67Ksq1hUL'
                'h0PXKkzyNbsW2rWEln')
        d = request.urlopen(link)
        request.urlretrieve(link, URL_FILE)
        print('Enlaces actualizados con fecha', d.info()['Date'])
        return

    def get_urls_from_file(self):
        try:
            with open(URL_FILE, 'r') as f:
                fileLines = f.readlines()
        except FileNotFoundError:
            print(
                'Si quieres descargar los videos de la Biblia en lengua de '
                f'señas chilena, en la carpeta {os.getcwd()} debes crear un'
                f'archivo llamado "{URL_FILE}" que contenga las URLs que '
                'desees descargar.\n\n')
            urls = []
        else:
            itemLines = [x.strip() for x in fileLines]
            urls = [x for x in itemLines
                    if os.path.basename(x).startswith('nwt_')
                    and x.startswith('http')]
        return urls

    def libros_disponibles_para_descarga(self, urls=None):
        if not urls:
            urls = self.urls
        indices = {get_book_index(url) for url in urls}
        return {indice: NUMERO_LIBRO[indice] for indice in indices}

    def libros_disponibles_descargados(self):
        for dirpath, dirnames, filenames in os.walk(DESCARGAS):
            indices = {get_book_index(filename) for filename in filenames
                       if filename.startswith('nwt_')}
            break
        return {indice: NUMERO_LIBRO[indice] for indice in indices}

    def get_urls_from_book_index(self, i):
        return [url for url in self.urls if int(get_book_index(url)) == int(i)]

    def get_nwt_videos_from_descargas(self):
        nwt_videos = []
        for dirpath, dirnames, filenames in os.walk(DESCARGAS):
            for filename in filenames:
                if filename.startswith('nwt_') \
                        and (filename.endswith('.mp4')
                             or filename.endswith('.m4v')):
                    nwt_videos.append(os.path.join(dirpath, filename))
        return nwt_videos

    def descargas_simultaneas(self, links):
        pool = Pool(4)
        self.m = pool.map(self.down, links)
        return

    def descargas_multiples(self, links):
        url_fail = list(map(self.down, links))
        return [x for x in url_fail if x is not None]

    def down(self, url):
        print(f'{url}', end='\t')
        try:
            d = request.urlopen(url, timeout=60)
            info = d.info()
        except URLError as e:
            print(e, 'URL NO VÁLIDO ')
            return url
        except timeout_error:
            print('Ha superado el tiempo de espera. No se ha podido descargar')
            return url
        path = os.path.join(DESCARGAS, info.get_filename())
        etag = info.get('ETag').replace('"', '')
        if os.path.exists(path) and os.stat(path).st_size == d.length:
            """No lo descargo, pero debo verificar db"""
            print('Ya estaba descargado')
            # print(f'ya existe y son del mismo tamaño mas encima {d.length}')
            if self.dbd.contains(
                    (Q.filename == os.path.basename(path))
                    & (Q.ETag == etag)):
                # print('coinciden etags. No hago nada')
                return
            elif self.dbd.contains(Q.filename == os.path.basename(path)):
                doc = self.dbd.search(Q.filename == os.path.basename(path))[0]
                if not doc.get('ETag'):
                    # print('Se ha descargado desde otra fuente, y '
                    #       'posiblemente se haya cortado. Actualizo ETag')
                    self.dbd.upsert({'ETag': etag, 'length': d.length},
                                    Q.filename == info.get_filename(),
                                    )
            else:
                # print('ya estaba descargado. No estaba en db, plt debo cortarlo')
                self.upsert_download(info, cortado=False)
                return
        else:
            # print('No existe o no coincide tamaño')
            if os.path.exists(path):
                os.remove(path)
            print('descargando', end=' ')
            try:
                request.urlretrieve(url, filename=path)
            except Exception as e:
                print(f'ERROR. No he podido descargar el enlace\n{url}\n'
                      f'Este es el mensaje de error:\n{e}')
                return url
                # raise Exception
            else:
                print('OK')
                self.upsert_download(info, cortado=False)
        return

    def upsert_download(self, info, cortado=False):
        self.dbd.upsert(
            {
                'filename': info.get_filename(),
                'ETag': info.get('ETag').replace('"', ''),
                'length': int(info.get('Content-Length')),
                'cortado': cortado,
                },
            Q.filename == info.get_filename())
        return

    def centro_cortes(self, nwt_videos, hwaccel=False):
        t0 = time.time()
        error_video = []
        self.versiculos = self.get_versiculos_cortados()
        for versiculo in self.versiculos:
            print(versiculo)
        for nwt_video in nwt_videos:
            print(f'\n{os.path.basename(nwt_video)}')
            if self.dbd.contains(Q.filename == os.path.basename(nwt_video)):
                descarga = self.dbd.search(
                    Q.filename == os.path.basename(nwt_video))[0]
            else:
                descarga = {}
            if descarga.get('length') != os.stat(nwt_video).st_size:
                """como no coinciden los tamaños, se asume que se
                descargaron de otra fuente. upsert sin ETag
                """
                self.dbd.upsert(
                    {
                        'filename': os.path.basename(nwt_video),
                        'ETag': '',
                        'length': os.stat(nwt_video).st_size,
                        'cortado': False,
                        },
                    Q.filename == os.path.basename(nwt_video)
                )
                descarga = self.dbd.search(
                    Q.filename == os.path.basename(nwt_video))[0]
            marcadores = self.get_marcadores(nwt_video)
            a_medias = False
            for marcador in marcadores:
                print(
                    f'{marcador["title"].replace("__", " ").replace("_", ":")}',
                    end='\t')
                if descarga.get('cortado') is not False \
                        and self.versiculos.get(marcador['title']):
                    print(f'ya estaba cortado')
                else:
                    color = self._verificaBordes(nwt_video, marcador['start'])
                    output = os.path.join(
                        CORTES, marcador["title"] + ext(nwt_video),
                        )
                    completed_process = self.cut_up(
                        nwt_video,
                        marcador['start'],
                        marcador['end'],
                        output,
                        color,
                        hwaccel,
                        )
                    if completed_process.returncode == 0:
                        print('cortado')
                    else:
                        print('Error al cortar\n'
                              f'{completed_process.stderr.decode()}\n')
                        error_video.append(output)
                        a_medias = True

            if not marcadores:
                error_video.append(nwt_video)

            if a_medias:
                self.dbd.upsert({'cortado': None,  # Parcialmente, o indeterminado
                                 'filename': os.path.basename(nwt_video)},
                                Q.filename == os.path.basename(nwt_video))
            else:
                self.dbd.upsert({'cortado': True,
                                 'filename': os.path.basename(nwt_video)},
                                Q.filename == os.path.basename(nwt_video))
        t1 = time.time()
        print(f'\n{t1 - t0}s transcurridos')
        for video in error_video:
            if os.path.dirname(video) == CORTES:
                try:
                    os.remove(video)
                except:
                    pass
        versiculos_sueltos = self.get_versiculos_sueltos()
        self.en_carpeta(versiculos_sueltos)
        return error_video

    def en_carpeta(self, versiculos):
        numeracion = self.is_numeracion()
        if numeracion is None:
            self.quitar_numeracion()
        for versiculo in versiculos:
            basename = os.path.basename(versiculo)
            book = basename.split('__')[0]
            newfolder = f'{LIBRO_NUMERO[book]}_{book}' if numeracion else book
            newdir = os.path.join(CORTES, newfolder)
            newdirfile = os.path.join(newdir, basename)

            if not os.path.exists(newdir):
                os.mkdir(newdir)
            if os.path.exists(newdirfile) and platform.system() == 'Windows':
                os.remove(newdirfile)
            os.rename(versiculo, newdirfile)

    def cut_up(self, nwt_video, start, end, output, color=None, hwaccel=False):
        cmd = [FFMPEG, '-y', '-loglevel', 'warning',
               '-hide_banner', '-ss', start]
        if hwaccel:
            cmd += ['-hwaccel', 'cuvid', '-c:v', 'h264_cuvid']
        cmd += ['-i', nwt_video, '-to', str(float(end) - float(start)),
                '-map_chapters', '-1', '-metadata', 'title=']
        if color:
            vf = (f'drawbox=x=0:y=0:w=170:h=720:color={color}:t=fill, '
                  f'drawbox=x=1110:y=0:w=170:h=720:color={color}:t=fill')
            cmd += ['-vf', vf]
        if hwaccel:
            cmd += ['-c:v', 'h264_nvenc']
        cmd += [output]

        # print(' '.join(cmd))
        # https://superuser.com/questions/1320389/updating-mp4-chapter-times-and-names-with-ffmpeg
        return subprocess.run(cmd, capture_output=True)

    def get_versiculos_cortados(self):
        versiculos = {}
        for dirpath, dirnames, filenames in os.walk(CORTES):
            for filename in filenames:
                if filename.endswith('.mp4') or filename.endswith('.m4v'):
                    versiculos.setdefault(woext(filename),
                                          os.path.join(dirpath, filename))
        return versiculos

    def get_versiculos_sueltos(self):
        for dirpath, dirnames, filenames in os.walk(CORTES):
            break
        versiculos = []
        for filename in filenames:
            if filename.endswith('.mp4') or filename.endswith('.m4v'):
                versiculos.append(os.path.join(CORTES, filename))
        return versiculos

    def get_marcadores(self, nwt_video):
        raw_json = probe_marcadores(nwt_video)
        marcadores = []
        for data in raw_json:
            t = data['tags']['title'].rstrip('\r').rstrip()
            title = self._define_nombre_video(t, nwt_video)
            if title:
                marcadores.append(
                    {
                        'start': data['start_time'],
                        'end': data['end_time'],
                        'title': title,
                    }
                )
        return marcadores

    def _verificaBordes(self, dir_file, ti):
        ruta = os.path.dirname(dir_file)
        snapshot = os.path.join(ruta, dir_file + '.jpg')
        cmd = [FFMPEG,
               '-y', '-hide_banner',
               '-ss', str(float(ti) + 0.5),
               '-i', dir_file,
               '-vframes', '1',
               snapshot]
        subprocess.run(cmd, capture_output=True)

        try:
            im = imageio.imread(snapshot)
        except OSError:

            return None
        else:
            color = tuple(im[20][20])
            if color == (0, 0, 0):
                corta = '0x{0[0]:x}{0[1]:x}{0[2]:x}'.format(im[165][360])
            else:
                corta = False
            os.remove(snapshot)
            return corta

    def _define_nombre_video(self, marcador, nwt_video):
        """
            MARCADOR                  |   OUTPUT
                                      |
            Gén. 1:1                  |   Genesis__01_01
            Juec. 4:14                |   Jueces__04_14
            Rut 1:4                   |   Rut__01_04
            1 Sam. 1:4                |   1Samuel__01_4
            Cant. de Cant. 2:5        |   Cantar_de_los_Cantares__02_05
            Inicio                    |   None
            Mateo                     |   None
            Mat. 1:1                  |   Mateo__01_01
            *Mat. 17:21 Nota          |   Mateo__17_21__Nota
            * Juan 5:4 Nota           |   Juan__05_04__Nota
            * Juan 8:1-11 Nota        |   Juan__08_1-11__Nota
            Hech. 8:37 Nota           |   Hechos__08_37__Nota
            Luc. 17:36 nota           |   Lucas__17_36__Nota
            1 Corintios               |   None
        =============================================================================
        nwt_video se utiliza para encontrar el libro de la Biblia
        """

        if len(marcador.split()) == 1:
            return None
            # marcador == 'Inicio' | 'Mateo' | 'Romanos' etc

        if not [s in string.digits for s in marcador[1:] if s in string.digits]:
            # marcador == '1 Corintios' | '2 Pedro'
            return None

        if marcador.split()[-1] in ['Nota', 'nota']:
            capvers = marcador.split()[-2]
            tieneNota = True
        else:
            capvers = marcador.split()[-1]
            tieneNota = False

        try:
            cap, vers = capvers.split(':')
        except ValueError:
            cap, vers = capvers.split('.')

        try:
            if int(cap) < 10:
                cap = '0{}'.format(cap)
        except ValueError:
            pass

        try:
            if int(vers) < 10:
                vers = '0{}'.format(vers)
        except ValueError:
            pass

        libro = get_book_name(nwt_video)

        if tieneNota:
            nombre = '{}__{}_{}__{}'.format(libro, cap, vers, 'Nota')
        else:
            nombre = '{}__{}_{}'.format(libro, cap, vers)
        return nombre


if __name__ == '__main__':
    Biblia = gestorBiblia()
    bienvenida = f'''
    Carpeta Descargas: '{DESCARGAS}'
    Carpeta Biblia por versículos: '{CORTES}'


    1. Actualizar la Biblia
    2. Descargar solo lo que falte
    3. Cortar solo lo que falte
    4. Cortar un video específico
    5. Actualizar URLs de videos
    6. Salir

    Elige una opción: '''
    print(bienvenida, end='')
    nwt_videos = Biblia.get_nwt_videos_from_descargas()
    urls = Biblia.urls
    opc = input()
    error_url = []
    error_video = []
    if opc == '1':
        error_url = Biblia.descargas_multiples(urls)
        error_video = Biblia.centro_cortes(nwt_videos)
    elif opc == '2':
        error_url = Biblia.descargas_multiples(urls)
    elif opc == '3':
        error_video = Biblia.centro_cortes(nwt_videos)
    elif opc == '3 hw':
        error_video = Biblia.centro_cortes(nwt_videos, hwaccel=True)
    elif opc == '4':
        # video = input('Copia las rutas de los videos separadas por una coma \n'
        #               r'Por ejemplo: C:\mi\carpeta\video.mp4'
        #               '\n\n')
        pass
    if error_url:
        u = '\n'.join(error_url)
        print(f'\n\nNo se han podido descargar los siguientes enlaces:\n{u}')
    if error_video:
        v = '\n'.join(error_video)
        print(f'\nNo se han podido cortar los siguientes videos:\n{v}')
