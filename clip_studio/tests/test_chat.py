"""Clip Studio chat-reaction finder: reducing a chat replay, spikes, paid messages and the reading match, privacy and paging. No network: YouTube is a fake."""
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('creator_studio_chat_test', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
suite = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = suite
spec.loader.exec_module(suite)
from creator_studio_chat_test import clip_studio  # noqa: E402
from creator_studio_chat_test.clip_studio import chat as C, source as S  # noqa: E402

VID = 'bbbbbbbbbbb'
DURATION = 1800
SECRET_CHANNEL = 'UCsecretchannelid0000000'
SECRET_PHOTO = 'https://yt4.ggpht.com/secret-photo=s32'
SAID = [(80, 'We are about to open the final chest.'), (112, 'And it contains absolutely nothing at all.'), (170, 'Thank you Pippa Longname for the dragon fruit donation.'),
        (200, 'Someone asks whether the purple frog speedrun record can be broken tonight.'), (260, 'The purple frog speedrun is impossible honestly.'),
        (900, 'Now back to the story.')]


def runs(*parts):
    return {'runs': [{'text': p} if isinstance(p, str) else p for p in parts]}


def common(author, ident):
    return {'id': ident, 'timestampUsec': '1', 'authorName': {'simpleText': author}, 'authorExternalChannelId': SECRET_CHANNEL, 'authorPhoto': {'thumbnails': [{'url': SECRET_PHOTO}]}}


def line(offset, renderer, body, wrap='addChatItemAction'):
    action = {wrap: {'item': {renderer: body}}} if wrap == 'addChatItemAction' else {wrap: body}
    return json.dumps({'clickTrackingParams': 'x', 'replayChatItemAction': {'actions': [action], 'videoOffsetTimeMsec': str(offset)}})


def text_line(offset, author, message, ident=None):
    body = {**common(author, ident or 'id%d%s' % (offset, author)), 'message': message if isinstance(message, dict) else runs(message)}
    return line(offset, 'liveChatTextMessageRenderer', body)


def replay():
    """A 30 minute stream: about 1 message every 3 s, a burst of reactions at 120 s after the 'nothing at all' line, one at 600 s, plus every kind of paid item."""
    out = [line(0, 'liveChatViewerEngagementMessageRenderer', {'id': 'welcome', 'message': runs('Live chat replay is on.')})]
    for n in range(0, DURATION, 3):
        out.append(text_line(n * 1000, 'viewer%d' % (n % 7), 'just chatting here %d' % n))
    for k in range(40):  # the 120 s burst: plenty of laughing, one custom emoji, one unicode emoji
        out.append(text_line(120000 + k * 400, 'fan%d' % k, runs('LMAOOOOO ' if k % 2 else 'lol lol ', {'emoji': {'emojiId': 'UCx/abc', 'shortcuts': [':face-blue-smiling:'], 'isCustomEmoji': True}}, ' ', {'emoji': {'emojiId': '\U0001F602'}}), 'burst%d' % k))
    for k in range(25):  # a smaller, later burst about a word
        out.append(text_line(600000 + k * 500, 'other%d' % k, 'WOW that was insane @someone http://spam.example/x', 'late%d' % k))
    for k in range(60):  # a chat game: command spam at 1000 s that is not a reaction
        out.append(text_line(1000000 + k * 300, 'gamer%d' % k, '!play', 'cmd%d' % k))
    out.append(text_line(5000, 'viewer1', 'just chatting here 0', 'id0viewer1'))  # same id as an earlier message: counted once
    out.append(text_line(5000, 'viewer1', 'just chatting here 0', 'id0viewer1'))
    out.append(text_line(-3000, 'early', 'before the stream began', 'pre'))
    out.append('this line is not json')
    out.append('{"replayChatItemAction": {"videoOffsetTimeMsec": "abc", "actions": []}}')
    out.append(line(165000, 'liveChatPaidMessageRenderer', {**common('@PippaLongname', 'sc1'), 'purchaseAmountText': {'simpleText': '$5.00'}, 'message': runs('Mail me at pippa@example.com or see https://example.com/me')}))
    out.append(line(195000, 'liveChatPaidMessageRenderer', {**common('@Nobody', 'sc2'), 'purchaseAmountText': {'simpleText': 'EUR 2.00'}, 'message': runs('Can the purple frog speedrun record be broken tonight?')}))
    out.append(line(300000, 'liveChatPaidMessageRenderer', {**common('@Silent', 'sc3'), 'purchaseAmountText': {'simpleText': '$1.00'}, 'message': runs('Zebra quartz jumbled sphinx waltz')}))
    out.append(line(400000, 'liveChatPaidStickerRenderer', {**common('@StickerFan', 'st1'), 'purchaseAmountText': {'simpleText': '$2.00'}, 'sticker': {'accessibility': {'accessibilityData': {'label': 'Happy cat'}}}}))
    out.append(line(500000, 'liveChatMembershipItemRenderer', {**common('@NewMember', 'm1'), 'headerSubtext': runs('Welcome to the crew!')}))
    out.append(line(700000, 'liveChatSponsorshipsGiftPurchaseAnnouncementRenderer', {**common('@Gifter', 'g1'), 'header': {'liveChatSponsorshipsHeaderRenderer': {'authorName': {'simpleText': '@Gifter'}, 'primaryText': runs('Sent ', '5', ' Channel memberships')}}}))
    out.append(line(701000, 'liveChatSponsorshipsGiftRedemptionAnnouncementRenderer', {**common('@Recipient', 'g2'), 'message': runs('received a gift')}))
    out.append(line(750000, 'giftMessageViewModel', {'id': 'gift1', 'text': {'content': 'comboed x2 Star for 4 Jewels'}, 'authorName': {'content': '@JewelFan '}, 'authorAvatar': {'avatarViewModel': {'image': {'sources': [{'url': SECRET_PHOTO}]}}}}))
    out.append(line(800000, 'liveChatPaidMessageRenderer', {**common('@Late', 'sc4'), 'purchaseAmountText': {'simpleText': '$3.00'}, 'message': runs('Vermilion octopus hurricane')}))
    return '\n'.join(out) + '\n'


def transcript_json3():
    events = [{'tStartMs': 0, 'dDurationMs': 99999, 'id': 1}]
    for at, sentence in SAID:
        events.append({'tStartMs': at * 1000, 'dDurationMs': 4000, 'segs': [{'utf8': sentence}]})
    return json.dumps({'events': events})


class FakeYouTube:
    calls = []
    status = 'was_live'
    chat_text = None  # None: the video has no chat replay
    subtitles = True

    def __init__(self, settings=None):
        pass

    def info(self, vid):
        self.calls.append(('info', vid))
        return {'id': vid, 'title': 'A stream', 'channel': 'Someone', 'duration': DURATION, 'live_status': self.status, 'language': 'en', 'chapters': [], 'subtitles': {'live_chat': [1]},
                'automatic_captions': {'en-orig': [1], 'en': [1]} if self.subtitles else {}}

    def captions(self, vid, track, automatic, folder):
        path = Path(folder) / 'captions.json3'
        path.write_text(transcript_json3())
        return path

    def chat(self, vid, folder):
        self.calls.append(('chat', vid))
        if self.chat_text is None:
            return None
        path = Path(folder) / 'chat-raw.live_chat.json'
        path.write_text(self.chat_text, encoding='utf-8')
        return path


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        storage = types.ModuleType('plugins.plugin_storage')

        def plugin_data_dir(name):
            folder = self.base / 'profile' / 'plugin-data' / name
            folder.mkdir(parents=True, exist_ok=True)
            return folder
        storage.plugin_data_dir = plugin_data_dir
        FakeYouTube.calls, FakeYouTube.status, FakeYouTube.chat_text, FakeYouTube.subtitles = [], 'was_live', replay(), True
        for patcher in (mock.patch.dict(sys.modules, {'plugins': types.ModuleType('plugins'), 'plugins.plugin_storage': storage}), mock.patch.object(S, 'YouTube', FakeYouTube)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def call(self, name, **args):
        return json.loads(clip_studio.invoke(name, args))

    def project(self):
        return self.call('clips_open', url=VID)['project_id']

    def folder(self, pid):
        return self.base / 'profile/plugin-data/creator-studio-clips/projects' / pid


class ReplayReadingTests(unittest.TestCase):
    def test_reduce_keeps_text_and_paid_and_counts_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'raw.json'
            path.write_text(replay(), encoding='utf-8')
            chat = C.reduce_replay(path)
        kinds = [p['kind'] for p in chat['paid']]
        self.assertEqual(kinds, ['super_chat', 'super_chat', 'super_chat', 'super_sticker', 'membership', 'membership_gift', 'gift', 'super_chat'])
        self.assertEqual(chat['unreadable_lines'], 2)
        self.assertEqual(chat['before_video_start'], 1)
        self.assertEqual(chat['gift_redemptions'], 1)
        self.assertEqual(sum(1 for t, m in chat['text'] if m == 'just chatting here 0'), 2)  # the same id twice counts once (plus the real first message)
        self.assertEqual(chat['paid'][0]['message'], 'Mail me at [email] or see [link]')
        gift, sticker, member = chat['paid'][5], chat['paid'][3], chat['paid'][4]
        self.assertEqual((gift['author'], gift['amount']), ('@Gifter', 'Sent 5 Channel memberships'))
        self.assertEqual((sticker['amount'], sticker['message']), ('$2.00', 'Happy cat'))
        self.assertEqual((member['amount'], member['author']), ('Welcome to the crew!', '@NewMember'))
        saved = json.dumps(chat)
        for secret in (SECRET_CHANNEL, SECRET_PHOTO, 'viewer3', 'fan7'):
            self.assertNotIn(secret, saved)  # ordinary authors, channel ids and pictures never reach the saved copy

    def test_emoji_runs_and_words(self):
        message = C._runs(runs('LMAOOO ', {'emoji': {'emojiId': 'UC/x', 'shortcuts': [':face-blue-smiling:'], 'isCustomEmoji': True}}, {'emoji': {'emojiId': '\U0001F602'}}))
        self.assertEqual(message, 'LMAOOO :face-blue-smiling: \U0001F602')
        self.assertEqual(C.words_of(message + ' lmao LMAO @bob http://x.example the'), ['lmao', ':face-blue-smiling:', '\U0001F602'])
        self.assertEqual(C.words_of('The and a'), [])

    def test_spikes_are_found_against_the_streams_own_rate(self):
        times = [n * 3000 for n in range(600)] + [120000 + k * 400 for k in range(40)]
        times.sort()
        found = C.find_spikes(times, 30, 5)
        self.assertEqual(found['spikes'][0][0], 120)  # the burst starts at 120 s
        self.assertEqual(C.find_spikes([n * 3000 for n in range(600)], 30, 5)['spikes'], [])  # steady chat has none


class ChatToolTests(Fixture):
    def test_fetches_once_and_finds_spikes_with_what_was_said_before(self):
        pid = self.project()
        out = self.call('clips_chat', project_id=pid, kind='spikes')
        self.assertEqual(FakeYouTube.calls.count(('chat', VID)), 1)
        self.assertTrue(out['fetched_now'])
        first = out['spikes']['items'][0]
        self.assertTrue(119 <= first['start'] <= 124, first)
        self.assertGreater(first['times_usual'], 2.5)
        words = [w for w, _ in first['common_words']]
        self.assertIn('lol', words)
        self.assertIn('lmao', words)
        self.assertIn(':face-blue-smiling:', words)
        before = ' '.join(s['text'] for s in first['said_before'])
        self.assertIn('contains absolutely nothing', before)  # said at 112 s, 5 to 20 s before the burst
        self.assertNotIn('final chest', before)  # said at 80 s: more than 20 s before
        second = self.call('clips_chat', project_id=pid, kind='spikes')
        self.assertFalse(second['fetched_now'])
        self.assertEqual(FakeYouTube.calls.count(('chat', VID)), 1)  # saved copy used
        self.call('clips_chat', project_id=pid, refresh=True)
        self.assertEqual(FakeYouTube.calls.count(('chat', VID)), 2)

    def test_second_spike_and_paging(self):
        pid = self.project()
        page = self.call('clips_chat', project_id=pid, kind='spikes', limit=1)['spikes']
        self.assertEqual((len(page['items']), page['next_offset'], page['total']), (1, 1, 2))
        later = self.call('clips_chat', project_id=pid, kind='spikes', limit=1, offset=1)['spikes']
        self.assertTrue(599 <= later['items'][0]['start'] <= 604)
        self.assertIsNone(later['next_offset'])
        self.assertIn('wow', [w for w, _ in later['items'][0]['common_words']])
        window = self.call('clips_chat', project_id=pid, kind='spikes', start='9:00', end='11:00')['spikes']
        self.assertEqual([r['start'] // 100 for r in window['items']], [6])
        only = self.call('clips_chat', project_id=pid, kind='spikes', query='wow')['spikes']
        self.assertEqual(only['total'], 1)

    def test_paid_messages_reading_match_and_no_reading(self):
        pid = self.project()
        paid = self.call('clips_chat', project_id=pid, kind='paid', limit=50)['paid']
        by_author = {p['author']: p for p in paid['items']}
        self.assertEqual(paid['total'], 8)
        self.assertEqual([p['start'] for p in paid['items']], sorted(p['start'] for p in paid['items']))
        named = by_author['@PippaLongname']
        self.assertEqual((named['amount'], named['kind'], named['at']), ('$5.00', 'super_chat', '2:45'))
        self.assertEqual(named['reading']['start'], 170.0)
        self.assertIn('name is spoken', named['reading']['basis'])
        self.assertNotIn('pippa@example.com', named['message'])
        said = by_author['@Nobody']['reading']  # message words repeated by the streamer
        self.assertEqual(said['start'], 200.0)
        self.assertIn('purple', said['basis'])
        self.assertEqual(by_author['@Silent']['reading'], 'no reading found')
        self.assertEqual(by_author['@Late']['reading'], 'no reading found')  # the words are never spoken
        self.assertEqual(by_author['@Gifter']['kind'], 'membership_gift')
        self.assertEqual(by_author['@StickerFan']['kind'], 'super_sticker')
        self.assertEqual((by_author['@JewelFan']['kind'], by_author['@JewelFan']['amount']), ('gift', 'comboed x2 Star for 4 Jewels'))
        self.assertEqual(self.call('clips_chat', project_id=pid, kind='paid', query='purple')['paid']['total'], 1)
        self.assertEqual(self.call('clips_chat', project_id=pid, kind='paid', start=600)['paid']['total'], 3)
        one = self.call('clips_chat', project_id=pid, kind='paid', limit=3)['paid']
        self.assertEqual((len(one['items']), one['next_offset']), (3, 3))
        rest = self.call('clips_chat', project_id=pid, kind='paid', limit=3, offset=6)['paid']
        self.assertEqual((len(rest['items']), rest['next_offset']), (2, None))

    def test_privacy_no_ordinary_authors_ids_or_pictures(self):
        pid = self.project()
        everything = ''.join(json.dumps(self.call('clips_chat', project_id=pid, **a)) for a in ({}, {'kind': 'spikes'}, {'kind': 'paid', 'limit': 50}, {'kind': 'rate'}, {'query': 'lol'}))
        for secret in (SECRET_CHANNEL, SECRET_PHOTO, 'ggpht', 'viewer3', 'fan7', 'other3', 'pippa@example.com', 'someone', 'spam.example'):
            self.assertNotIn(secret, everything)
        self.assertIn('@PippaLongname', everything)  # paid names are returned
        stored = ''.join(p.read_text(errors='replace') for p in self.folder(pid).iterdir() if p.is_file() and p.name.startswith('chat'))
        self.assertNotIn(SECRET_CHANNEL, stored)
        self.assertEqual(list(self.folder(pid).glob('chat-raw.*')), [])  # raw replay deleted after reducing
        description = clip_studio.TOOLS['clips_chat'][0]
        self.assertIn('untrusted', description)
        self.assertIn('never who wrote what', description)

    def test_chat_game_commands_are_left_out_of_spikes_but_counted(self):
        pid = self.project()
        out = self.call('clips_chat', project_id=pid, kind='spikes')
        self.assertEqual([r['start'] // 100 for r in out['spikes']['items']], [1, 6])
        commands = self.call('clips_chat', project_id=pid)['chat']['commands']
        self.assertEqual((commands['messages'], commands['common'][0]), (60, ['!play', 60]))
        self.assertTrue(any(900 <= r['start'] <= 1010 for r in self.call('clips_chat', project_id=pid, kind='spikes', include_commands=True)['spikes']['items']))
        self.assertTrue(any(900 <= r['start'] <= 1010 for r in self.call('clips_chat', project_id=pid, kind='spikes', query='!play')['spikes']['items']))

    def test_overview_rate_and_next_line(self):
        pid = self.project()
        out = self.call('clips_chat', project_id=pid)
        self.assertEqual({'chat', 'rate', 'spikes', 'paid', 'next', 'privacy', 'notice', 'project_id', 'title', 'fetched_now', 'transcript'}, set(out))
        self.assertIn('clips_transcript', out['next'])
        self.assertLessEqual(len(out['spikes']['items']), 5)
        self.assertLessEqual(len(out['paid']['items']), 5)
        self.assertEqual(out['paid']['total'], 8)
        rate = self.call('clips_chat', project_id=pid, kind='rate', limit=50)['rate']
        self.assertEqual(rate['step_seconds'], 60)
        self.assertEqual(max(r['per_minute'] for r in rate['items']), rate['busiest_step']['per_minute'])
        self.assertEqual(rate['busiest_step']['start'], 120)

    def test_works_before_a_transcript_exists(self):
        FakeYouTube.subtitles = False
        pid = self.project()
        out = self.call('clips_chat', project_id=pid)
        self.assertNotIn('error', out)
        self.assertIn('none yet', out['transcript'])
        self.assertIsNone(out['spikes']['items'][0]['said_before'])
        self.assertIn('not checked', out['paid']['items'][0]['reading'])

    def test_plain_refusals(self):
        pid = self.project()
        FakeYouTube.chat_text = None
        self.assertIn('no chat replay', self.call('clips_chat', project_id=pid)['error'])
        data = json.loads((self.folder(pid) / 'project.json').read_text())
        for status, words in (('is_live', 'still on air'), ('post_live', 'only just ended'), ('is_upcoming', 'has not started')):
            data['live_status'] = status
            (self.folder(pid) / 'project.json').write_text(json.dumps(data))
            self.assertIn(words, self.call('clips_chat', project_id=pid)['error'])
        FakeYouTube.calls.clear()
        self.assertEqual(FakeYouTube.calls, [])  # a stream still on air never reached YouTube
        FakeYouTube.chat_text = ''
        data['live_status'] = 'was_live'
        (self.folder(pid) / 'project.json').write_text(json.dumps(data))
        self.assertIn('no chat replay', self.call('clips_chat', project_id=pid)['error'])  # empty file counts as none

    def test_local_recording_and_bad_arguments(self):
        media = self.base / 'recording.mp3'
        media.write_bytes(b'x')
        with mock.patch.object(S, 'probe', return_value={'duration': 10.0, 'video': False, 'audio': True, 'width': None, 'height': None}):
            pid = self.call('clips_open', media_path=str(media))['project_id']
        self.assertIn('has no chat', self.call('clips_chat', project_id=pid)['error'])
        pid = self.project()
        for bad in ({'kind': 'funny'}, {'limit': 0}, {'limit': 99}, {'offset': -1}, {'window_seconds': 5}, {'start': 50, 'end': 10}, {'query': ''}, {'refresh': 'yes'}, {'color': 'red'}):
            self.assertIn('error', self.call('clips_chat', project_id=pid, **bad), bad)
        self.assertIn('Unknown project_id', self.call('clips_chat', project_id='../../x')['error'])

    def test_extension_is_registered(self):
        self.assertIn('clips_chat', clip_studio.TOOLS)
        self.assertIn('clips_chat', clip_studio._HANDLERS)
        description, properties, required = clip_studio.TOOLS['clips_chat']
        self.assertEqual(required, ['project_id'])
        self.assertTrue(description.isascii())


if __name__ == '__main__':
    unittest.main()
