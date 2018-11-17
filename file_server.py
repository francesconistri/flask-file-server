import json
import mimetypes
import os
import re
import stat
from datetime import datetime

import furl
import humanize
from cached_property import cached_property
from flask import (
    Flask,
    Response,
    make_response,
    render_template,
    request,
    send_file,
)
from flask.views import MethodView
from werkzeug import secure_filename
import jinja2

app = Flask(__name__, static_url_path="/assets", static_folder="assets")
root = os.path.expanduser("~")

ignored = [
    ".bzr",
    "$RECYCLE.BIN",
    ".DAV",
    ".DS_Store",
    ".git",
    ".hg",
    ".htaccess",
    ".htpasswd",
    ".Spotlight-V100",
    ".svn",
    "__MACOSX",
    "ehthumbs.db",
    "robots.txt",
    "Thumbs.db",
    "thumbs.tps",
]
datatypes = {
    "audio": "m4a,mp3,oga,ogg,webma,wav",
    "archive": "7z,zip,rar,gz,tar",
    "image": "gif,ico,jpe,jpeg,jpg,png,svg,webp",
    "pdf": "pdf",
    "quicktime": "3g2,3gp,3gp2,3gpp,mov,qt",
    "source": "atom,bat,bash,c,cmd,coffee,css,hml,js,json,java,less,markdown,md,php,pl,py,rb,rss,sass,scpt,swift,scss,sh,xml,yml,plist",
    "text": "txt",
    "video": "mp4,m4v,ogv,webm",
    "website": "htm,html,mhtm,mhtml,xhtm,xhtml",
}
icontypes = {
    "fa-music": "m4a,mp3,oga,ogg,webma,wav",
    "fa-archive": "7z,zip,rar,gz,tar",
    "fa-picture-o": "gif,ico,jpe,jpeg,jpg,png,svg,webp",
    "fa-file-text": "pdf",
    "fa-film": "3g2,3gp,3gp2,3gpp,mov,qt,mp4,m4v,ogv,webm",
    "fa-code": (
        "atom,plist,bat,bash,c,cmd,coffee,css,hml,js,json,java,less,markdown,md,php,pl,py,rb,rss,sass,scpt,swift,scss,sh,xml,yml"
    ),
    "fa-file-text-o": "txt",
    "fa-globe": "htm,html,mhtm,mhtml,xhtm,xhtml",
}


@app.template_filter("size_fmt")
def size_fmt(size):
    return humanize.naturalsize(size)


@app.template_filter("time_fmt")
def time_desc(timestamp):
    mdate = datetime.fromtimestamp(timestamp)
    str = mdate.strftime("%Y-%m-%d %H:%M:%S")
    return str


@app.template_filter("data_fmt")
def data_fmt(filename):
    t = "unknown"
    for type, exts in datatypes.items():
        if filename.split(".")[-1] in exts:
            t = type
    return t


@app.template_filter("icon_fmt")
def icon_fmt(filename):
    i = "fa-file-o"
    for icon, exts in icontypes.items():
        if filename.split(".")[-1] in exts:
            i = icon
    return i


@app.template_filter("humanize")
def time_humanize(timestamp):
    mdate = datetime.utcfromtimestamp(timestamp)
    return humanize.naturaltime(mdate)


@jinja2.contextfilter
def set_param(context, param, value):
    f = furl.furl(request.full_path)
    f.args[param] = value
    return f.url


app.jinja_env.filters["set_param"] = set_param


def partial_response(path, start, end=None):
    file_size = os.path.getsize(path)

    if end is None:
        end = file_size - 1
    length = end - start + 1

    with open(path, "rb") as fd:
        fd.seek(start)
        bytes = fd.read(length)
    assert len(bytes) == length

    response = Response(
        bytes,
        206,
        mimetype=mimetypes.guess_type(path)[0],
        direct_passthrough=True,
    )
    response.headers.add(
        "Content-Range", "bytes {0}-{1}/{2}".format(start, end, file_size)
    )
    response.headers.add("Accept-Ranges", "bytes")
    return response


def get_range(request):
    range = request.headers.get("Range")
    m = re.match(r"bytes=(?P<start>\d+)-(?P<end>\d+)?", range)
    if m:
        start = m.group("start")
        end = m.group("end")
        start = int(start)
        if end is not None:
            end = int(end)
        return start, end
    else:
        return 0, None


def iter_recursive_files(path):
    for _root, _dirs, _files in os.walk(path):

        for _filename in _files:

            filepath = os.path.join(path, _root, _filename)

            yield File(filepath, path)


def iter_files(path):
    for filename in os.listdir(path):
        yield File(os.path.join(path, filename), path)


def sorted_contents(contents, sorting):
    if not sorting:
        return contents
    reverse = sorting.startswith("-")
    key = sorting.lstrip("-")
    return sorted(
        contents, reverse=reverse, key=lambda f: getattr(f, key, None)
    )


def paginate(contents, page, page_size=100):
    try:
        page = int(page)
        page_size = int(page_size)
    except Exception:
        return contents
    start = page * page_size
    end = start + page_size
    return contents[start:end]


class File:
    def __init__(self, full_path, base_path):
        self.path = full_path
        self.name = os.path.basename(self.path)

    def get_absolute_url(self):
        return os.path.relpath(self.path, root)

    @cached_property
    def stat(self):
        try:
            return os.stat(self.path)
        except Exception:
            try:
                return os.stat(self.path)
            except Exception:
                return None

    @cached_property
    def type(self):
        if self.stat.st_mode and (
            stat.S_ISDIR(self.stat.st_mode) or stat.S_ISLNK(self.stat.st_mode)
        ):
            return "dir"
        return "file"

    @property
    def mtime(self):
        return self.stat and self.stat.st_mtime

    @property
    def size(self):
        return self.stat and self.stat.st_size

    def ignored(self):
        return self.name in ignored

    def hidden(self):
        return self.name.startswith(".")


class PathView(MethodView):
    def get_page(self):
        try:
            return int(request.args.get("page"))
        except (ValueError, TypeError):
            return 0

    def get_page_size(self):
        try:
            return int(request.args.get("page_size"))
        except (ValueError, TypeError):
            return 100

    def get(self, p=""):
        hide_dotfile = request.args.get(
            "hide-dotfile", request.cookies.get("hide-dotfile", "no")
        )

        recursive = request.args.get("recursive") == "yes"
        sorting = request.args.get("sorting")

        path = os.path.join(root, p)
        if os.path.isdir(path):
            contents = []
            total = {"size": 0, "dir": 0, "file": 0}
            if recursive:
                iterator = iter_recursive_files(path)
            else:
                iterator = iter_files(path)
            for file in iterator:
                if file.ignored():
                    continue
                if hide_dotfile == "yes" and file.hidden():
                    continue
                if not file.stat:
                    continue
                total[file.type] += 1
                total["size"] += file.size

                contents.append(file)

            contents = sorted_contents(contents, sorting)
            contents = paginate(
                contents, self.get_page(), page_size=self.get_page_size()
            )
            response_content = render_template(
                "index.html",
                path=p,
                page=self.get_page(),
                page_size=self.get_page_size(),
                contents=contents,
                total=total,
                hide_dotfile=hide_dotfile,
                recursive=recursive,
            )
            res = make_response(response_content, 200)
            res.set_cookie("hide-dotfile", hide_dotfile, max_age=16070400)
        elif os.path.isfile(path):
            if "Range" in request.headers:

                start, end = get_range(request)
                res = partial_response(path, start, end)
            else:
                res = send_file(path)
                res.headers.add("Content-Disposition", "attachment")
        else:
            res = make_response("Not found", 404)
        return res

    def post(self, p=""):
        path = os.path.join(root, p)
        info = {}
        if os.path.isdir(path):
            files = request.files.getlist("files[]")
            for file in files:
                try:
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(path, filename))
                except Exception as e:
                    info["status"] = "error"
                    info["msg"] = str(e)
                else:
                    info["status"] = "success"
                    info["msg"] = "File Saved"
        else:
            info["status"] = "error"
            info["msg"] = "Invalid Operation"
        res = make_response(json.JSONEncoder().encode(info), 200)
        res.headers.add("Content-type", "application/json")
        return res


path_view = PathView.as_view("path_view")
app.add_url_rule("/", view_func=path_view)
app.add_url_rule("/<path:p>", view_func=path_view)

if __name__ == "__main__":
    app.run("0.0.0.0", 8000, threaded=True, debug=False)
