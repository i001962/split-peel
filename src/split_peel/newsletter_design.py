"""Email-safe Final Whistle design and fictional demonstration editions."""
from html import escape as esc
from pathlib import Path
import re

NAVY = '#050712'
LIME = '#a2e634'
BERRY = '#bd195d'


def safe_url(value):
    if not re.fullmatch(r'https://[^\s<>"\']+', value):
        raise ValueError('Email links must use HTTPS')
    return esc(value, quote=True)


def paragraph(value):
    return '<p style="margin:0 0 16px;font-size:16px;line-height:1.7;color:#30364b">' + esc(str(value)) + '</p>'


def render_email(*, title, hook, watch, unsubscribe, facts=(), leagues=(), squad_notes=(), snapshot_label='', example=False, thumbnail=None, sections=(), x_url='https://x.com/closertoyes'):
    """600px table layout, inline styles, system fonts, no JavaScript or embedded video."""
    watch, unsubscribe = safe_url(watch), safe_url(unsubscribe)
    x_url = safe_url(x_url)
    thumbnail = thumbnail or ('https://i.ytimg.com/vi/WXxWz3Bb6GY/hqdefault.jpg' if example else None)
    hero = f'<a href="{watch}"><img src="{safe_url(thumbnail)}" alt="Watch Final Whistle on YouTube" width="536" style="display:block;width:100%;max-width:536px;height:auto;border:0;border-radius:8px;margin:22px 0 16px"></a>' if thumbnail else ''
    editorial = ''.join('<h2 style="margin:28px 0 12px;font-size:21px;color:#10162b">'+esc(section['heading'])+'</h2>'+''.join(paragraph(line) for line in section['paragraphs']) for section in sections)
    warning = '''<tr><td style="background:#fff1cf;padding:13px 28px;color:#604610;font-size:12px;line-height:1.6"><strong>DESIGN EXAMPLE</strong> · Fictional managers, scores and squad notes. The watch button opens the real show channel. This is not a live Match Report.</td></tr>''' if example else ''
    sections = ''
    if facts:
        sections += '<h2 style="margin:30px 0 14px;font-size:21px;color:#10162b">From the desk</h2>'
        sections += ''.join(paragraph(f) for f in facts)
    for league in leagues:
        own = league.get('own')
        stats = ''
        if own:
            stats = '''<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f0f3e9;border:1px solid #dce5ca;border-radius:10px;margin:16px 0"><tr>'''
            for label, value in [('POSITION', own['rank']), ('GW POINTS', own['event_total']), ('TOTAL', own['total'])]:
                stats += f'<td width="33%" align="center" style="padding:18px 4px"><span style="font-size:10px;letter-spacing:1px;color:#56613d">{label}</span><br><strong style="font-size:27px;line-height:1.5;color:#18210b">{esc(str(value))}</strong></td>'
            stats += '</tr></table>'
        sections += f'''<div style="border-top:2px solid {NAVY};margin-top:28px;padding-top:22px"><p style="margin:0 0 8px;color:{BERRY};font-size:10px;letter-spacing:2px;font-weight:bold">YOUR LEAGUE</p><h2 style="margin:0 0 10px;color:#10162b;font-size:23px">{esc(league['name'])}</h2>{stats}'''
        sections += ''.join(paragraph(n) for n in league.get('notes', []))
        sections += f'<p style="font-size:11px;line-height:1.6;color:#657087;margin:12px 0">{esc(snapshot_label)}</p>'
        sections += f'<a href="{safe_url(league["url"])}" style="font-size:14px;font-weight:bold;color:{BERRY};text-decoration:underline">Read your league report →</a></div>'
    if squad_notes:
        sections += '<div style="margin-top:28px;padding:20px;background:#f5f5f8;border-left:4px solid #bd195d"><h2 style="font-size:18px;margin:0 0 12px;color:#10162b">On your squad radar</h2>'
        sections += ''.join(paragraph(note) for note in squad_notes)
        sections += '<p style="font-size:11px;line-height:1.6;color:#657087;margin:0">Last publicly available squad. ' + esc(snapshot_label) + '</p></div>'
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="light"><title>{esc(title)} — Final Whistle</title>
<style>@media only screen and (max-width:620px){{.email-shell{{width:100%!important}}.email-pad{{padding-left:22px!important;padding-right:22px!important}}.headline{{font-size:31px!important}}}}</style></head>
<body style="margin:0;padding:0;background:#e9ebf0;font-family:Arial,Helvetica,sans-serif;-webkit-text-size-adjust:100%">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{esc(hook[:160])}</div>
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" bgcolor="#e9ebf0"><tr><td align="center" style="padding:28px 8px">
<table role="presentation" class="email-shell" width="600" cellspacing="0" cellpadding="0" style="width:100%;max-width:600px;background:#ffffff;border:1px solid #dfe3eb">
<tr><td class="email-pad" bgcolor="{NAVY}" style="padding:28px 32px 24px;border-top:5px solid {LIME}">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td><a href="https://final-whistle.app/" style="color:#ffffff;font-size:27px;letter-spacing:-1px;font-weight:900;text-decoration:none">FINAL <span style="color:{LIME}">WHISTLE.</span></a><p style="margin:7px 0 0;color:#a6abd0;letter-spacing:2px;font-size:10px">THE MATCH REPORT · WITH SPLIT &amp; PEEL</p></td><td width="76" align="right"><img src="https://final-whistle.app/art/split.png" width="48" height="48" alt="Split" style="display:block;border:0;width:48px;height:48px"></td></tr></table>
</td></tr>{warning}
<tr><td class="email-pad" style="padding:30px 32px 32px">
<p style="color:{BERRY};font-size:11px;font-weight:bold;letter-spacing:2px;margin:0 0 14px">FRESH FROM THE FINAL WHISTLE DESK</p>
<h1 class="headline" style="font-size:36px;line-height:1.12;letter-spacing:-1px;color:#10162b;margin:0 0 18px">{esc(title)}</h1>
{paragraph(hook)}{hero}
<table role="presentation" cellspacing="0" cellpadding="0" style="margin:22px 0 6px"><tr><td bgcolor="{LIME}" style="border-radius:6px"><a href="{watch}" style="display:inline-block;padding:16px 24px;color:#142006;font-size:15px;font-weight:bold;text-decoration:none;border:1px solid {LIME};border-radius:6px">▶ Watch Final Whistle on YouTube</a></td></tr></table>
<p style="margin:12px 0 0;font-size:12px;color:#657087">The whistle goes. The takes stay loud.</p>{editorial}{sections}
</td></tr>
<tr><td class="email-pad" bgcolor="#10152c" style="padding:25px 32px"><p style="font-size:11px;letter-spacing:2px;color:{LIME};margin:0 0 9px">KEEP THE CONVERSATION GOING</p><p style="margin:0;color:#ffffff;font-size:16px;line-height:1.6">Split keeps the receipts between shows.<br><a href="{x_url}" style="color:#ffffff;font-weight:bold;text-decoration:underline">Follow @closertoyes on X →</a></p></td></tr>
<tr><td class="email-pad" style="padding:22px 32px 26px;background:#f6f7fa;font-size:11px;line-height:1.8;color:#657087">Final Whistle with Split &amp; Peel<br>You're receiving the Match Report because you joined Final Whistle.<br><a href="https://final-whistle.app/profile" style="color:#47516c">Your profile</a> &nbsp;·&nbsp; <a href="{unsubscribe}" style="color:#47516c">Unsubscribe</a></td></tr>
</table></td></tr></table></body></html>'''


def examples():
    common = dict(watch='https://www.youtube.com/@split-peel', unsubscribe='https://final-whistle.app/join', example=True,
                  snapshot_label='Illustrative GW8 snapshot · scores and notes are fictional.',
                  sections=[dict(heading='The talking point', paragraphs=['A tiny decision can own your whole weekend. This sample section makes space for the football story behind the new episode.']), dict(heading='Split’s notebook', paragraphs=['One clear takeaway, a little argument, and a reason to watch the desk work it out. The final wording follows each issue’s editorial instructions.'])])
    return {
        '01-farcaster': dict(common, title='The armband has entered the chat.', hook='One captain. Two very different weekends. Split has the numbers; Peel has already blamed the weather.',
             facts=['The new episode follows the decisions that turn a sensible team into a very loud group chat.'],
             leagues=[dict(name='Farcaster Fantasy League', own=dict(rank=7,event_total=68,total=512), notes=['Your fictional team climbed three places. The gap to sixth is now four points. Enough to keep checking.'], url='https://final-whistle.app/report/143466')],
             squad_notes=['Sample player A — a fitness update worth checking before the deadline. This note demonstrates placement, not real player news.']),
        '02-multiple-leagues': dict(common, title='Two leagues. One very smug manager.', hook='A good gameweek travels well. Here is how the same fictional team looks in two different tables.',
             facts=['Watch the desk argue through the fine line between a brave captaincy call and a lucky escape.'],
             leagues=[dict(name='Farcaster Fantasy League', own=dict(rank=3,event_total=81,total=548),notes=['Up two places. The fictional leader is nine points away.'],url='https://final-whistle.app/report/143466'),
                      dict(name='Sunday League Office XI — example', own=dict(rank=1,event_total=81,total=548),notes=['Top of the fictional office table. Monday morning has become a presentation opportunity.'],url='https://final-whistle.app/')]),
        '03-show-only': dict(common, title='The desk is open. Your table can wait.', hook='A fresh Final Whistle episode, one very specific football argument, and Peel finding a way to make it personal.',
             facts=['This is the lightweight edition: a strong reason to watch, a useful takeaway, and room to breathe.', 'When league data is unavailable, we send the shared show edition and leave out unverified numbers.'])
    }


def write_examples(out):
    out.mkdir(parents=True, exist_ok=True)
    links = []
    for name, data in examples().items():
        (out / (name + '.html')).write_text(render_email(**data), encoding='utf-8')
        links.append(f'<a href="{name}.html" style="display:block;padding:22px;background:white;border:1px solid #d8dce5;margin:14px 0;border-radius:10px;color:#11182c;text-decoration:none"><strong>{esc(data["title"])}</strong><br><span style="color:#657087">{esc(name)} · Open email preview →</span></a>')
    (out / 'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Final Whistle email examples</title><body style="background:#e9ebf0;font-family:Arial,sans-serif;margin:0"><main style="max-width:700px;margin:50px auto;padding:24px"><p style="color:#bd195d;font-size:12px;letter-spacing:2px">FINAL WHISTLE · EMAIL STUDIO</p><h1 style="font-size:42px;color:#10152c">The Match Report.</h1><p>Three example editions using the production email template. All manager data is fictional.</p>'+''.join(links)+'</main></body></html>', encoding='utf-8')
    return {'directory': str(out), 'examples': list(examples())}
