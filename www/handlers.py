# -*- coding:utf8 -*-

__author__ = 'Parle'

'''
url handlers
'''


import re, time, json, logging, hashlib, base64, asyncio

from coroweb import get, post
from models import User, Comment, Blog, next_id
from config import configs
from apis import APIValueError, APIResourceNotFoundError, Page

from aiohttp import web 

COOKIE_NAME = "websession"
_COOKIE_KEY = configs.session.secret

def check_admin(request):
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError()


def get_page_index(page_str):
    p = 1
    try:
        p = int(page_str)
    except ValueError as e:
        pass
    if p < 1:
        p = 1
    return p


def text2html(text):
    lines = map(lambda s: '<p>%s</p>' % s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'), filter(lambda s: s.strip() != '', text.split('\n')))
    return ''.join(lines)


def user2cookie(user, max_age):
    '''
    Generate cookie str by user
    '''
    # build cookie string by: id-expores-shal
    expires = str(int(time.time() + max_age))
    s = '%s-%s-%s-%s' %(user.id, user.passwd, expires, _COOKIE_KEY)
    L = [user.id, expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]
    return '-'.join(L)


@asyncio.coroutine
def cookie2user(cookie_str):
    '''
    Parse cookie and load user if cookie is valid
    '''
    if not cookie_str:
        logging.info("cookie_str is null!")
        return None
    try:
        L = cookie_str.split('-')
        if len(L) != 3:
            logging.info("cookie form is error!")
            return None
        uid, expires, sha1 = L
        if int(expires) < time.time():
            logging.info("expires is error!")
            return None
        
        user = yield from User.find(uid)
        
        if user is None:
            logging.info("user is not exist!")
            return None
        s = "%s-%s-%s-%s" %(uid, user.passwd, expires, _COOKIE_KEY)
        if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
            logging.info("invaild sha1!")
            return None
        user.passwd = "******"
        return user
    except Exception as e:
        logging.exception(e)
        return None


@get('/')
def index(request):
    summary = 'Lorem ipsum dolor sit amet, consectetur adipisicing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
    blogs = [
        Blog(id='1', name='Test Blog', summary=summary, created_at=time.time()-120),
        Blog(id='2', name='Something New', summary=summary, created_at=time.time()-3600),
        Blog(id='3', name='Learn Swift', summary=summary, created_at=time.time()-7200)
    ]
    print('\n\n\n***',blogs,'\n\n\n')
    return {
        '__template__': 'blogs.html',
        'blogs': blogs
    }


@get('/register')
def register():
    return {
            '__template__': 'register.html'
        }


@get('/signin')
def signin():
    return {
            '__template__': 'signin.html'
        }

@post('/api/authenticate')
def authenticate(*, email, passwd):
    if not email:
        raise APIValueError('email', 'Invaild email.')
    if not passwd:
        raise APIValueError('passwd', 'Invaild passwd.')
    users = yield from User.findAll('email=?', [email])
    if len(users) == 0:
        raise APIValueError('email', 'Email not exist.')
    user = users[0]

    sha1 = hashlib.sha1()
    sha1.update(user.id.encode('utf-8'))
    sha1.update(b':')
    sha1.update(passwd.encode('utf-8'))
    
    if user.passwd != sha1.hexdigest():
        raise APIValueError('passwd', 'Invalid Password.')

    # authenticate ok, set cookie
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r


@get('/signout')
def signout(request):
    referer = request.headers.get('Referer')
    r = web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME, '-*deleted*-', max_age=0, httponly=True)
    logging.info('user signout out.')
    return r


@get('/manage/')
def manage():
    return 'redirect:/manage.comments'


@get('/manage/comments')
def manage_comments(*, page='1'):
    return {
            '__template__': 'manage_comments.html',
            'page_index': get_page_index(page)
    }


@get('/manage/users')
def manage_users(*, page='1'):
    return {
            '__template__': 'manage_users.html',
            'page_index':get_page_index(page)
    }


@get('/manage/blogs')
def manage_blogs(*, page='1'):
    return {
        '__template__': 'manage_blogs.html',
        'page_index':get_page_index(page)
    }


@get('/manage/blogs/create')
def manage_create_blog():
    return {
        '__template__': 'manage_blog_edit.html',
        'id': '',
        'action': '/api/blogs'
    }
    
    
@get('/manage/blogs/edit')
def manage_edit_blog(*, id):
    return {
            '__template__': 'manage_blog_edit.html',
            'id': id,
            'action': '/api/blog/%s' % id
    }


RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')


@post('/api/users')
@asyncio.coroutine
def api_register_user(*, email, name, passwd):
    if not name or not name.strip():
        raise APIValueError('name')
    if not email or not RE_EMAIL.match(email):
        raise APIValueError('email')
    if not passwd or not RE_SHA1.match(passwd):
        raise APIValueError('password')

    users = yield from User.findAll('email=?', [email])

    if len(users) > 0:
        raise APIError('register:faild', 'email', 'Email is already in use')
    uid = next_id()
    sha1_passwd = '%s:%s' %(uid, passwd)
    user = User(id=uid, name=name.strip(), email=email, passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(), 
        image='http://www.gravatar.com/avatar/%s?d=mm&s=120' % hashlib.md5(email.encode('utf-8')).hexdigest())
    yield from user.save()
    
    # make session cookie:
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r


@get('/api/blogs')
def api_blogs(*, page='1'):
    page_index = get_page_index(page)
    num = yield from Blog.findNumber('count(id)')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, blogs=())
    blogs = yield from Blog.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, blogs=blogs)


@get('/api/blogs/{id}')
@asyncio.coroutine
def api_get_blog(*, id):
    blog = yield from Blog.find(id)
    return blog


@post('/api/blogs')
@asyncio.coroutine
def api_create_blog(request, *, name, summary, content):
    check_admin(request)
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'content cannot be empty.')
    blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, user_image=request.__user__.image, name=name.strip(), summary=summary.strip(), content=content.strip())
    yield from blog.save()
    return blog


@post('/api/blogs/{id}')
@asyncio.coroutine
def api_update_blog(request, *, name, summary, content):
    check_admin(request)
    blog = yield from Blog.find(id)
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'content cannot be empty.')

    blog.name = name.strip()
    blog.summary = summary.strip()
    blog.content = content.strip()
    yield from blog.update()
    return blog


@post('/api/blogs/{id}/delete')
@asyncio.coroutine
def apt_delete_blog(request, *, id):
    check_admin(request)
    blog = yield from Blog.find(id)
    yield from blog.remove()
    return dict(id=id)





# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

@get('/api/users')
@asyncio.coroutine
def api_get_users():
    users = yield from User.findAll(orderBy='created_at desc')
    for u in users:
        u.passwd = '******'
    return dict(users=users)

