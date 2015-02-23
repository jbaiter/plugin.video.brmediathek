import logging
from datetime import datetime
from pprint import pprint

import requests

LOGGER = logging.getLogger('brmediathek')

def _get_link(document, key):
    return requests.get(document['_links'][key]['href']).json()


def _parse_time(timestr):
    if timestr is None:
        return None
    return datetime.strptime(timestr.split('+')[0], '%Y-%m-%dT%H:%M:%S')


class Livestream(object):
    def __init__(self, data):
            self.url = data['_links']['stream']['href']
            self.stream_type = data['type'].lower()
            self.quality = (int(data['quality'])
                            if data.get('quality') else None)

    def __repr__(self):
        return unicode(self).encode('utf-8')

    def __unicode__(self):
        return (u"<Stream url='{}', type='{}', quality={}>"
                .format(self.url, self.stream_type, self.quality))

class Videofile(object):
    def __init__(self, data):
        self.url = data['_links']['download']['href']
        self.size = data['size']
        self.video_info = {k: v for k, v in data.iteritems()
                        if k.endswith("Video") or k.startswith('frame')}
        self.audio_info = {k: v for k, v in data.iteritems()
                        if k.endswith("Audio")}

    def __repr__(self):
        return unicode(self).encode('utf-8')

    def __unicode__(self):
            return (u"<Video with {vcodec}@{vbitrate}, {acodec}@{abitrate}, "
                    u"{width}x{height}>"
                    .format(vcodec=self.video_info['codecVideo'],
                            vbitrate=self.video_info['bitrateVideo'],
                            acodec=self.audio_info['codecAudio'],
                            abitrate=self.audio_info['bitrateAudio'],
                            width=self.video_info['frameWidth'],
                            height=self.video_info['frameHeight']))


class ItemBase(object):
    def __init__(self, data):
        self._rawdata = data
        docprop = data['documentProperties']
        self.box_title = data.get("boxTitle")
        self.topline = data.get('topline', docprop.get('br-core:topline'))
        self.headline = data.get('headline', docprop.get('br-core:azHeadline'))
        self.geoprotected = docprop.get('br-core:geoProtected', False)
        self.has_livestream = docprop.get('br-core:hasLiveStream', False)
        self.has_ondemand = docprop.get('br-core:hasOnDemand', False)
        self.description = (docprop.get('br-core:metaDescription') or
                            docprop.get('br-core:teaserText'))
        self.uid = docprop.get('sophora:id')
        self.contribution_title = docprop.get('br-core:contributionTitle')
        if 'teaserImage' in data:
            self.teaserimage = {
                qualid[5:] if 'image' in qualid else qualid: obj['href']
                for qualid, obj in data['teaserImage']['_links'].items()
                if 'image' in qualid or qualid == 'original'
            }
        else:
            self.teaserimage = {}

    @property
    def title(self):
        return ": ".join((self.topline, self.headline))

    def __repr__(self):
        return unicode(self).encode('utf-8')

    def __unicode__(self):
        return u"<ItemBase \"{0}\">".format(self.title)


class Channel(ItemBase):
    def __init__(self, data):
        super(Channel, self).__init__(data)
        self.channel_title = self._rawdata['channelTitle']
        self.region_title = self._rawdata['regionTitle']

    @property
    def title(self):
        if self.region_title:
            return ": ".join((self.channel_title, self.region_title))
        else:
            return self.channel_title

    @property
    def playables(self):
        full_meta = _get_link(self._rawdata, 'self')
        # FIXME: Make geozone configurable
        return {a['type'].lower(): playable_factory(a)
                for a in full_meta['assets'] if a['geozone'] == 'DEUTSCHLAND'}

    def __unicode__(self):
        return u"<Channel \"{0}\">".format(self.title)


class Video(ItemBase):
    def __init__(self, data):
        super(Video, self).__init__(data)
        self.is_full_broadcast = (
            self._rawdata['documentProperties'].get('br-core:entireBroadcast'))
        self.start_date = _parse_time(self._rawdata.get('broadcastStartDate'))
        self.end_date = _parse_time(self._rawdata.get('broadcastEndDate'))


    @property
    def playables(self):
        full_meta = _get_link(self._rawdata, 'self')
        return {a['type'].lower(): playable_factory(a)
                for a in full_meta['assets']}

    def __unicode__(self):
        return u"<Video \"{0}\">".format(self.title)


class Series(ItemBase):
    def __init__(self, data):
        super(Series, self).__init__(data)

    @property
    def videos(self):
        full_meta = _get_link(self._rawdata, 'self')
        has_teasers = ('_embedded' in full_meta and
                       len(full_meta['_embedded']['teasers']) > 1)
        if has_teasers:
            yield [Video(x) for x in full_meta['_embedded']['teasers']]
            if 'next' in full_meta['_embedded'].get('_links', {}):
                next_url = full_meta['_embedded']['_links']['next']['href']
            else:
                next_url = None
        elif 'latestVideos' in full_meta['_links']:
            next_url = full_meta['_links']['latestVideos']['href']
        while next_url:
            video_data = requests.get(next_url).json()
            yield [Video(x) for x in video_data['_embedded']['teasers']]
            if 'next' in video_data['_embedded'].get('_links', {}):
                next_url = video_data['_embedded']['_links']['next']['href']
            else:
                next_url = None

    @property
    def title(self):
        return self.headline

    def __unicode__(self):
        return u"<Series \"{0}\">".format(self.title)


class Broadcast(ItemBase):
    def __init__(self, data):
        super(Broadcast, self).__init__(data)
        self.start_date = _parse_time(self._rawdata.get('broadcastStartDate'))
        self.end_date = _parse_time(self._rawdata.get('broadcastEndDate'))
        self.series_name = self._rawdata['documentProperties'].get(
            'br-core:broadcastSeriesTitle')

    @property
    def playables(self):
        return {a['type'].lower(): playable_factory(a)
                for a in self._fullmeta['assets']}

    @property
    def series(self):
        return Series(_get_link(self._fullmeta['broadcast']['broadcastSeries'],
                      'self'))

    @property
    def _fullmeta(self):
        if not hasattr(self, '__fullmeta'):
            self.__fullmeta = _get_link(self._rawdata, 'video')
        return self.__fullmeta

    @property
    def title(self):
        if self.series_name and not self.series_name == self.headline:
            return ": ".join((self.series_name, self.headline))
        else:
            return self.headline

    def __unicode__(self):
        return u"<Broadcast \"{0}\">".format(self.title)


def item_factory(data):
    item_type = data['documentProperties']['jcr:primaryType']
    if item_type in ('br-core-nt:broadcastSeries', 'br-core-nt:indexPage'):
        return Series(data)
    elif item_type == 'br-core-nt:broadcast':
        return Broadcast(data)
    elif item_type == 'br-core-nt:video':
        return Video(data)
    elif item_type == 'br-core-nt:liveDashboard':
        return Channel(data)
    else:
        raise ValueError("Unknown item type: " + item_type)


def playable_factory(data):
    if 'stream' in data['_links']:
        return Livestream(data)
    else:
        return Videofile(data)


def has_playable(data):
    docprops = data['documentProperties']
    return bool(
        docprops.get('br-core:onDemand') or
        docprops.get('br-core:download')
    )


class BRMediathek(object):
    START_URL = "http://www.br.de/system/halTocJson.jsp"
    CHANNELS = {'ARD-alpha': 'channel_28487',
                'Bayerisches Fernsehen': 'channel_28107'}

    def __init__(self):
        toc_url = (requests.get(self.START_URL).json()
                   ['medcc']['version']['1']['href'])
        self._toc = requests.get(toc_url).json()['_links']
        self._epg_days = {
            datetime.strptime(k, '%Y-%m-%d'): v['href'] for k, v in
            (requests.get(self._toc['epg']['href']).json()['epgDays']['_links']
            .iteritems())
        }

    def _get_category_generator(self, t_val, q_val):
        next_url = next(
            x['_links']['boxIndexPage']
            for x in self._home_data['_embedded']['teasers']
            if x['boxTitle'] != 'Livestream')['href'].split('?')[0]
        while next_url:
            data = requests.get(next_url.split('?')[0],
                                params={'t': t_val, 'q': q_val}).json()
            if 'teasers' in data['_embedded']:
                yield [item_factory(t) for t in data['_embedded']['teasers']]
            if 'next' in data['_embedded']['_links']:
                next_url = data['_embedded']['_links']['next']['href']
            else:
                next_url = None

    @property
    def _home_data(self):
        if not hasattr(self, "__home_data"):
            self.__home_data = requests.get(self._toc['home']['href']).json()
        return self.__home_data

    @property
    def available_dates(self):
        return sorted([k for k in self._epg_days if k <= datetime.now()])

    @property
    def livestreams(self):
        index_url = next(
            x['_links']['boxIndexPage']
            for x in self._home_data['_embedded']['teasers']
            if x['boxTitle'] == 'Livestream')['href']
        return [Channel(d) for d in (requests.get(index_url)
                                             .json()['_embedded']['teasers'])
                if _parse_time(d['broadcastStartDate']) < datetime.now()]

    @property
    def editors_choice(self):
        return self._get_category_generator("tags", "Mediathek-Tagestipp")

    @property
    def most_viewed(self):
        return self._get_category_generator("social", "mostViewed")

    @property
    def best_rated(self):
        return self._get_category_generator("social", "bestRated")

    @property
    def most_recommended(self):
        return self._get_category_generator("social", "mostRecommended")

    @property
    def web_exclusive(self):
        return self._get_category_generator("category", "web-exklusiv")

    @property
    def web_previews(self):
        return self._get_category_generator("category", "vorab-im-web")

    def show_by_letter(self, letter='a'):
        idx = requests.get(self._toc['broadcastSeriesAz']['href']).json()
        items = _get_link(idx['az'], letter.lower())['_embedded']['teasers']
        return [item_factory(itm) for itm in items]

    def show_by_date(self, date, channel="Bayerisches Fernsehen"):
        if channel not in self.CHANNELS:
            raise ValueError("Invalid channel, must be one of {}"
                             .format(self.CHANNELS.keys()))
        channel = self.CHANNELS[channel]
        broadcasts = (requests.get(self._epg_days[date]).json()
                      ['channels'][channel]['broadcasts'])
        out = []
        for b in broadcasts:
            date = _parse_time(b['broadcastStartDate'])
            skip = (date > datetime.now() or
                    '_links' not in b or
                    'video' not in b['_links'])
            if not skip:
                out.append(item_factory(b))
        return out

    def search(self, query, page=1, per_page=24):
        data = (requests.get(self._toc['search']['href'].format(term=query),
                              params={'page': page,
                                      'resultsPerPage': per_page}).json())
        if data['resultCount'] == 0:
            return []
        return (data['resultCount'],
                [item_factory(itm) for itm in data['_embedded']['teasers']
                 if has_playable(itm)])
