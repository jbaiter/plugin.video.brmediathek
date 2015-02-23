from __future__ import division

import os
import string
import sys
from datetime import datetime
from multiprocessing.dummy import Pool as ThreadPool

try:
    import xbmc
    import xbmcaddon
    __addon__ = xbmcaddon.Addon(id='plugin.video.brmediathek')
    __cwd__ = (xbmc.translatePath(__addon__.getAddonInfo('path'))
                   .decode("utf-8"))
    sys.path.insert(0, os.path.join(__cwd__, 'resources', 'lib'))
except ImportError:
    pass

from resources.lib.brmediathek import BRMediathek, Broadcast
from resources.lib.xbmcswift2 import Plugin


plugin = Plugin()
mediathek = BRMediathek()
pool = ThreadPool(8)

VIDEO_QUAL='premium'
ITEMS_PER_PAGE=24

#FIXME: Pagination works in xbmcswift CLI, not in Kodi :-(

def _get_thumbnail(obj):
    for qual in ('256q', '256', 'original'):
        if qual in obj.teaserimage:
            return obj.teaserimage[qual]


def _get_duration(obj):
    if obj.end_date and obj.start_date:
        return int((obj.end_date - obj.start_date).total_seconds())


def _get_streaminfo(playable, duration):
    vidinf = playable.video_info
    audinf = playable.audio_info
    return {
        'video': {
            'codec': vidinf['codecVideo'],
            'aspect': int(vidinf['frameWidth'])/int(vidinf['frameHeight']),
            'width': int(vidinf['frameWidth']),
            'height': int(vidinf['frameHeight']),
            'duration': duration},
        'audio': {
            'codec': audinf['codecAudio'],
            'language': 'de'}}


def _make_item(britem):
    itm = {
        'thumbnail': _get_thumbnail(britem),
        'path': britem.playables[VIDEO_QUAL].url,
        'stream_info': _get_streaminfo(britem.playables[VIDEO_QUAL],
                                       _get_duration(britem)),
        'info': {
            'plot': britem.description,
            'plotoutline': britem.description},
        'properties': {'Fanart_Image': britem.teaserimage['original']},
        'is_playable': True}
    if isinstance(britem, Broadcast):
        itm['label'] = " - ".join(
            (datetime.strftime(britem.start_date, '%H:%M'), britem.title))
    else:
        itm['label'] = britem.title
    if britem.start_date:
        itm['info']['aired'] = datetime.strftime(britem.start_date, '%Y-%m-%d')
    return itm


@plugin.route('/livestreams')
def livestreams():
    return pool.map(
        lambda c: {'label': c.title,
                   'thumbnail': _get_thumbnail(c),
                   'path': c.playables['hls'].url,
                   'properties': {'Fanart_Image': c.teaserimage['original']},
                   'is_playable': True},
        mediathek.livestreams)


@plugin.route('/shows')
def shows():
    return [{'label': letter.upper(),
             'path': plugin.url_for('show_by_letter', letter=letter)}
            for letter in string.lowercase]


@plugin.route('/shows/<letter>')
def show_by_letter(letter):
    shows = mediathek.show_by_letter(letter)
    show_store = plugin.get_storage('shows')
    for show in shows:
        if show.uid  in show_store:
            continue
        show_store[show.uid] = show
    return [{'label': s.title,
             'thumbnail': _get_thumbnail(s),
             'path': plugin.url_for(display_show, showid=s.uid, paged=False),
             'properties': {'Fanart_Image': s.teaserimage['original']}}
            for s in shows]


def _paginate(func, initial_gen, is_paged):
    if not is_paged or not hasattr(func, '_gen'):
        func._gen = initial_gen
        try:
            func._next = next(func._gen)
        except StopIteration:
            func._next = None


@plugin.route('/show/<showid>', name='show_details_firstpage')
@plugin.route('/show/<showid>/<paged>')
def display_show(showid, paged=False):
    paged = (paged == "True")
    show = plugin.get_storage('shows')[showid]
    _paginate(display_show, show.videos, paged)
    itms = pool.map(_make_item, display_show._next)
    try:
        display_show._next = next(display_show._gen)
    except StopIteration:
        display_show._next = None
    if display_show._next:
        itms.append({'label': 'Mehr...',
                    'path': plugin.url_for(display_show, showid=showid,
                                            paged=True)})
        return plugin.finish(itms, update_listing=True)
    else:
        return itms


@plugin.route('/archive')
def dates():
    return [{'label': datetime.strftime(d, '%x'),
             'path': plugin.url_for(show_by_date, date=d.toordinal())}
            for d in mediathek.available_dates]


@plugin.route('/archive/<date>')
def show_by_date(date):
    if not isinstance(date, datetime):
        date = datetime.fromordinal(int(date))
    return pool.map(_make_item, mediathek.show_by_date(date))


@plugin.route('/categories/<category>', name='category_details_firstpage')
@plugin.route('/categories/<category>/<paged>')
def show_by_category(category, paged=False):
    paged = (paged == "True")
    _paginate(show_by_category, getattr(mediathek, category), paged)
    itms = pool.map(_make_item, show_by_category._next)
    try:
        show_by_category._next = next(show_by_category._gen)
    except StopIteration:
        show_by_category._next = None
    if show_by_category._next:
        itms.append({'label': 'Mehr...',
                    'path': plugin.url_for(show_by_category, category=category,
                                           paged=True)})
        return plugin.finish(itms, update_listing=paged)
    else:
        return itms


@plugin.route('/search', name='search_start')
@plugin.route('/search/<query>/<page>')
def search(query=None, page="1"):
    page = int(page)
    if not query:
        query = plugin.keyboard()
    total_num, britems = mediathek.search(query, page, ITEMS_PER_PAGE)
    itms = pool.map(_make_item, britems)
    if (page*ITEMS_PER_PAGE) < total_num:
        itms.append({'label': 'Mehr...',
                     'path': plugin.url_for('search', query=query,
                                            page=page+1)})
        return plugin.finish(itms, update_listing=page!=1)
    else:
        return itms


@plugin.route('/')
def index():
    return [
        {'label': plugin.get_string(30001),
         'path': plugin.url_for('livestreams')},
        {'label': plugin.get_string(30002),
         'path': plugin.url_for('shows')},
        {'label': plugin.get_string(30003),
         'path': plugin.url_for('dates')},
        {'label':plugin.get_string(30004),
         'path': plugin.url_for('category_details_firstpage',
                                category='editors_choice')},
        {'label': plugin.get_string(30005),
         'path': plugin.url_for('category_details_firstpage',
                                category='most_viewed')},
        {'label': plugin.get_string(30006),
         'path': plugin.url_for('category_details_firstpage',
                                 category='best_rated')},
        {'label': plugin.get_string(30007),
         'path': plugin.url_for('category_details_firstpage',
                                category='most_recommended')},
        {'label': plugin.get_string(30008),
         'path': plugin.url_for('category_details_firstpage',
                                category='web_exclusive')},
        {'label': plugin.get_string(30009),
         'path': plugin.url_for('category_details_firstpage',
                                category='web_previews')},
        {'label': plugin.get_string(30010),
         'path': plugin.url_for('search_start')}]


if __name__ == '__main__':
    plugin.run()
