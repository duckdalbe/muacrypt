# -*- coding: utf-8 -*-
# vim:ts=4:sw=4:expandtab

"""Mime message parsing and manipulation functions for Autocrypt usage. """

from __future__ import unicode_literals, print_function
import email.parser
import base64
import quopri
from .myattr import attrs, attrib, attrib_bytes_or_none, attrib_text_or_none
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
from email.generator import _make_boundary
import six

if six.PY3:
    from email.generator import BytesGenerator
    from email import message_from_bytes, message_from_binary_file
else:
    from email.generator import Generator as BytesGenerator
    from email import message_from_string as message_from_bytes  # noqa
    from email import message_from_file as message_from_binary_file # noqa


def decode_keydata(ascii_keydata):
    return base64.b64decode(ascii_keydata)


# slighly hacky way to get a byte string out of a message

class MyBytesIO(six.BytesIO):
    def write(self, s):
        if isinstance(s, six.text_type):
            s = s.encode("ascii")
        return six.BytesIO.write(self, s)


def msg2bytes(msg):
    f = MyBytesIO()
    BytesGenerator(f).flatten(msg)
    return f.getvalue()


# main functions

def make_ac_header_value(addr, keydata, prefer_encrypt="nopreference"):
    assert keydata
    key = base64.b64encode(keydata) if isinstance(keydata, bytes) else keydata
    if isinstance(key, bytes):
        key = key.decode("ascii")
    l = ["addr=" + addr]
    if prefer_encrypt != "nopreference":
        l.append("prefer-encrypt=" + prefer_encrypt)
    l.append("keydata=\n" + indented_split(key))
    return "; ".join(l)


def indented_split(value, maxlen=78, indent="  "):
    assert "\n" not in value
    l = []
    for i in range(0, len(value), maxlen):
        l.append(indent + value[i:i + maxlen] + "\n")
    return "".join(l).rstrip()


def get_target_emailadr(msg):
    l = []
    tos = msg.get_all("to") + (msg.get_all("cc") or [])
    for realname, emailadr in email.utils.getaddresses(tos):
        l.append(emailadr)
    return l


def parse_email_addr(string):
    """ return the routable email address part from a email-field string.

    If the address is of type bytes and not ascii, it is returned in
    quoted printable encoding.
    """
    prefix, emailadr = email.utils.parseaddr(string)
    if isinstance(emailadr, bytes):
        emailadr = six.text_type(quopri.encodestring(emailadr))
    return emailadr


def parse_message_from_file(fp):
    return email.parser.Parser().parse(fp)


def parse_message_from_string(string):
    if isinstance(string, bytes):
        stream = six.BytesIO(string)
    else:
        stream = six.StringIO(string)
    return parse_message_from_file(stream)


def parse_one_ac_header_from_string(string):
    msg = parse_message_from_string(string)
    return parse_one_ac_header_from_msg(msg)


def parse_one_ac_header_from_msg(msg, FromList=None):
    if msg.get_content_type() == 'multipart/report':
        return ACParseResult(error="Ignoring 'multipart/report' message.")
    results = []
    err_results = []
    for ac_header_value in msg.get_all("Autocrypt") or []:
        r = parse_ac_headervalue(ac_header_value)
        if not r.error and (not FromList or r.addr in FromList):
            results.append(r)
        else:
            err_results.append(r)

    if len(results) == 1:
        return results[0]
    if len(results) > 1:
        return ACParseResult(error="more than one valid Autocrypt header found")
    if err_results:
        return err_results[0]
    else:
        return ACParseResult(error="no valid Autocrypt header found")


def parse_ac_headervalue(value):
    """ return a Result object with keydata/addr/prefer_encrypt/extra_attr/error
    attributes.

    If the error attribute is set on the result object then all
    other attribute values are undefined.
    """
    parts = filter(None, [x.strip() for x in value.split(";")])
    if not parts:
        return ACParseResult(error="empty header")

    result_dict = {"prefer_encrypt": "nopreference"}
    extra_attr = {}
    for x in parts:
        kv = x.split("=", 1)
        if not len(kv) == 2:
            return ACParseResult(error="malformed setting")
        name, value = [x.strip() for x in kv]
        if name == "keydata":
            try:
                value = decode_keydata("".join(value.split()))
            except Exception:
                return ACParseResult(error="failed to decode keydata")
        elif name == "prefer-encrypt":
            name = "prefer_encrypt"
            if value not in ("nopreference", "mutual"):
                return ACParseResult(error="unknown prefer-encryp setting '%s'" % value)
        elif name == "addr":
            pass
        elif name[0] != "_":
            return ACParseResult(error="unknown critical attr '%s'" % name)
        else:
            extra_attr[name] = value
            continue
        result_dict[name] = value
    for attr in ("keydata", "addr"):
        if attr not in result_dict:
            return ACParseResult(error="critical attr '%s' missing" % attr)
    return ACParseResult(extra_attr=extra_attr, **result_dict)


@attrs
class ACParseResult(object):
    keydata = attrib_bytes_or_none()
    addr = attrib_text_or_none()
    prefer_encrypt = attrib_text_or_none()
    extra_attr = attrib(default=None)
    error = attrib_text_or_none()


def gen_mail_msg(From, To, _extra=None, Autocrypt=None, Subject="testmail",
                 Date=None, _dto=False, MessageID=None, payload='Autoresponse\n',
                 charset=None):
    assert isinstance(To, (list, tuple))
    if MessageID is None:
        MessageID = make_msgid()

    if not isinstance(payload, list):
        msg = MIMEText(payload or '', _charset=charset)
    else:
        msg = MIMEMultipart()
        assert not payload

    msg['From'] = From
    msg['To'] = ",".join(To)
    msg['Message-ID'] = MessageID
    msg['Subject'] = Subject
    msg['Date'] = Date or formatdate()
    if _extra:
        for name, value in _extra.items():
            msg.add_header(name, value)
    if _dto:
        msg["Delivered-To"] = To[0]
    if Autocrypt:
        msg["Autocrypt"] = Autocrypt
    return msg


def gen_boundary():
    return _make_boundary()


def make_message(content_type, payload=None):
    msg = email.message.Message()
    del msg["MIME-Version"]
    msg["Content-Type"] = content_type
    if payload is not None:
        msg.set_payload(payload)
    return msg


def make_content_message_from_email(msg, _h=("content-transfer-encoding",)):
    newmsg = make_message(
        content_type=msg["Content-Type"],
        payload=msg.get_payload(decode=False)
    )
    for x in _h:
        if x in msg:
            newmsg[x] = msg[x]
    return newmsg


def transfer_non_content_headers(msg, newmsg):
    _ignore_headers = ["content-type", "mime-version", "content-transfer-encoding"]
    for header, value in msg.items():
        if header.lower() not in _ignore_headers:
            newmsg[header] = value


def get_delivered_to(msg, fallback_delivto=None):
    delivto = parse_email_addr(msg.get("Delivered-To"))
    if not delivto and fallback_delivto:
        delivto = parse_email_addr(fallback_delivto)
    if not delivto:
        raise ValueError("could not determine my own delivered-to address")
    return delivto


def make_displayable(string):
    if string is None:
        return ''
    if isinstance(string, six.text_type):
        return string
    assert isinstance(string, bytes)
    for enc in ["utf-8", "latin1"]:
        try:
            return string.decode(enc)
        except Exception:
            pass
    return six.text_type(quopri.encodestring(enc))


# adapted from ModernPGP:memoryhole/generators/generator.py which
# was adapted from notmuch:devel/printmimestructure
def render_mime_structure(msg, prefix='└'):
    '''msg should be an email.message.Message object'''
    stream = six.StringIO()
    mcset = msg.get_charset()
    fn = make_displayable(msg.get_filename())
    fname = ' [' + fn + ']'
    cset = '' if mcset is None else ' ({})'.format(mcset)
    disp = msg.get_params(None, header='Content-Disposition')
    if (disp is None):
        disposition = ''
    else:
        disposition = ''
        for d in disp:
            if d[0] in ['attachment', 'inline']:
                disposition = ' ' + d[0]

    if 'subject' in msg:
        subject = ' (Subject: %s)' % msg['subject']
    else:
        subject = ''
    if (msg.is_multipart()):
        print(prefix + '┬╴' + msg.get_content_type() + cset +
              disposition + fname, str(len(msg.as_string())) +
              ' bytes' + subject, file=stream)
        if prefix.endswith('└'):
            prefix = prefix.rpartition('└')[0] + ' '
        if prefix.endswith('├'):
            prefix = prefix.rpartition('├')[0] + '│'
        parts = msg.get_payload()
        i = 0
        while (i < len(parts) - 1):
            print(render_mime_structure(parts[i], prefix + '├'), file=stream)
            i += 1
        print(render_mime_structure(parts[i], prefix + '└'), file=stream)
        # FIXME: show epilogue?
    else:
        print(prefix + '─╴' + msg.get_content_type() + cset + disposition +
              fname, msg.get_payload().__len__().__str__(),
              'bytes' + subject, file=stream)
    return stream.getvalue().rstrip()
