# -*- coding: utf-8 -*-
# @File     : spider.py
# @Time     : 2021/05/14 18:48
# @Author   : Jckling

import pprint
import re
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlencode

from lxml import html
from mongoengine import Document, ListField, StringField, URLField, DateTimeField, IntField, DictField, BooleanField
from mongoengine import connect
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# docker volume create mongo-data
# docker run --name mongodb -p 27017:27017 -v mongo-data:/data/db -d mongo
# -e MONGO_INITDB_ROOT_USERNAME=admin -e MONGO_INITDB_ROOT_PASSWORD=password


# 查询相关参数
s = ['Relevance', 'Last Version Update', 'Release Date', 'Name', 'Views', 'Views Today', 'Downloads', 'Followers']
sortby = ['rank', 'time_edited', 'time_posted', 'name_slug', 'views', 'views_today', 'downloads', 'followers']
sortorder = ['desc', 'asc']
textools = "1,3,7,9,12,2,4,8,10"  # , -> %2C
cmtool = "11"
labels = ['Concept Matrix Pose', 'Textools Mods']
gender = ['Male', 'Unknown', 'Female', 'Unisex']
gender_zh = ['男', '未知', '女', '男女']
race = ['Roegadyn', 'Hrothgar', 'Elezen', 'Lalafell', 'Unknown', "Miqo'te", 'Au Ra', 'Viera', 'Midlander', 'Highlander']
race_zh = ['鲁加', '硌狮', '精灵', '拉拉菲尔', '未知', '猫魅', '敖龙', '维埃拉', '中原', '高地']


class Archive(Document):
    url = URLField(required=True, unique=True)  # url 地址
    mod_id = IntField(required=True, unique=True)  # 文件夹 <-> 文件
    title = StringField(required=True)  # 标题

    user = StringField()  # 用户
    user_link = URLField()  # 用户主页

    last_version_update = DateTimeField(required=True)  # 更新日期
    original_release_date = DateTimeField(required=True)  # 发布日期

    affects_replaces = StringField()  # 效果

    races = ListField()  # 种族
    genders = ListField()  # 性别
    tags = ListField()  # 标签

    views = IntField()  # 浏览量
    downloads = IntField()  # 下载量
    following = IntField()  # 订阅量

    images = ListField(required=True)  # 预览图

    info = DictField()  # 描述信息
    files = ListField()  # 文件

    nsfw = BooleanField(required=True)  # NSFW
    label = StringField(required=True)  # CMTool or TexTools


# 时间转换
def to_date(date_str):
    try:
        datetime_object = datetime.strptime(date_str, '%Y/%m/%d上午%I:%M:%S')
    except ValueError:
        datetime_object = datetime.strptime(date_str, '%Y/%m/%d下午%I:%M:%S') + timedelta(hours=12)
    return datetime_object


# 数字转换
def to_number(num_str):
    if '-' in num_str:
        return 0
    elif 'K' in num_str:
        return int(float(num_str[:-1]) * 1000)
    return int(num_str)


# 数据库中是否存在
def existed(url):
    if Archive.objects(url=url):
        return True
    return False


# 连接数据库
connect(host='mongodb://localhost:27017/test', tz_aware=False)


# 初始化 web driver
def init_driver():
    options = Options()
    options.add_argument("user-data-dir=C:\\Users\\linki\\AppData\\Local\\Google\\Chrome\\User Data")  # Chrome
    options.add_experimental_option("excludeSwitches", ["ignore-certificate-errors"])
    options.headless = True
    return webdriver.Chrome(options=options)


class Crawler:
    url = "https://www.xivmodarchive.com"

    def __init__(self):
        self.driver = init_driver()

    def search(self, label, sortby="rank", sortorder="desc", types="", nsfw=False, page=1):
        base = urljoin(self.url, "search")

        params = urlencode({"sortby": sortby, "sortorder": sortorder, "types": types, "nsfw": nsfw, "page": page})
        url = base + "?" + params
        print(url)

        # first page
        self.driver.get(url)

        # total pages
        tree = html.fromstring(self.driver.page_source)
        tmp = tree.xpath('//div[@class="row"]/div[@class="col-4"]/code[@class="text-light"]/text()')
        total, pages = re.findall(r'\d+', tmp[0])
        print("Total: {} in {} Pages".format(total, pages))

        # mods
        print("Page {} has ".format(page), end="")
        self._get_mods(label, nsfw, tree.xpath('//div[starts-with(@class, "mod-card")]/a'))

        # next page
        while page < int(pages):
            page += 1

            params = urlencode({"sortby": sortby, "sortorder": sortorder, "types": types, "nsfw": nsfw, "page": page})
            url = base + "?" + params
            print(url)

            self.driver.get(url)
            tree = html.fromstring(self.driver.page_source)

            print("Page {} has ".format(page), end="")
            self._get_mods(label, nsfw, tree.xpath('//div[starts-with(@class, "mod-card")]/a'))

        # close
        self._close_driver()

    def _get_mods(self, label, nsfw, mods):
        print(len(mods), "mods")

        for mod in mods:
            # 链接
            url = urljoin(self.url, mod.attrib['href'])
            mod_id = int(mod.attrib['href'].split('/')[-1])

            # 跳过已保存
            if existed(url):
                continue

            # time.sleep(random.randint(0, 3))
            print(url, end=" ")

            self.driver.get(url)
            tree = html.fromstring(self.driver.page_source)

            # 标题，作者，作者链接
            try:
                title = tree.xpath('//h1/text()')[0].strip()
            except IndexError:
                title = ""
            author = tree.xpath('//p[contains(@class, "lead")]/a')[0]
            user = author.text
            user_link = Crawler.url + author.attrib["href"]
            print(user, user_link)

            archive = Archive(label=label, nsfw=nsfw, mod_id=mod_id, url=url, title=title, user=user,
                              user_link=user_link)

            # 元数据
            metadata = tree.xpath('//div[contains(@class, "mod-meta-block")]')
            for m in metadata:
                name = m.text
                code = m.find('code')
                value = code.text
                values = code.findall('a')

                if 'Last Version Update' in name:
                    archive.last_version_update = to_date(value)

                if 'Original Release Date' in name:
                    archive.original_release_date = to_date(value)

                if 'Affects / Replaces' in name:
                    archive.affects_replaces = value

                if 'Races' in name:
                    archive.races = [v.text for v in values]
                    # archive.races = {v.text: Crawler.url + v.attrib["href"] for v in values}

                if 'Genders' in name:
                    archive.genders = [v.text for v in values]
                    # archive.genders = {v.text: Crawler.url + v.attrib["href"] for v in values}

                if 'Tags' in name:
                    archive.tags = [v.text for v in values]
                    # archive.tags = {v.text: Crawler.url + v.attrib["href"] for v in values}

            # 浏览，下载，关注
            t = '//span[contains(@class, "{}")]/div/span/text()'
            archive.views = to_number(tree.xpath(t.format("views"))[0])
            archive.downloads = to_number(tree.xpath(t.format("downloads"))[0])
            archive.following = to_number(tree.xpath(t.format("following"))[0])

            # 预览图
            preview = tree.xpath('//div[contains(@class, "carousel-item")]/a/img')
            images = []
            for i in preview:
                if "data-src" in i.attrib:
                    images.append(i.attrib["data-src"])
                else:
                    images.append(i.attrib["src"])
            archive.images = images

            # 信息
            tmp = tree.xpath('//div[@id="info"]')[0]
            info_titles = tmp.findall('p')
            info_values = tmp.findall('div')
            archive.info = {i.text_content().split(':')[0]: j.text_content() for i, j in zip(info_titles, info_values)}

            # 下载地址
            tmp = tree.xpath('//div[@id="files"]')[0]
            files = []
            for i in tmp.iter('a'):
                link = i.attrib["href"]
                if "private" in link:
                    files.append(Crawler.url + link)
                else:
                    files.append(link)
            archive.files = files

            # 保存数据
            archive.save()

    def _close_driver(self):
        self.driver.quit()


# 处理数据
def handle_document():
    driver = init_driver()
    for a in Archive.objects:
        if not a.user:
            search = Archive.objects(user_link=a.user_link)
            if search[0].user:
                a.user = search[0].user
            else:
                print(a.user_link)
                driver.get(a.user_link)
                tree = html.fromstring(driver.page_source)
                user = tree.xpath('//h1/text()')[0].strip()
                a.user = user
                for s in search:
                    s.user = user
                    s.save()

        if not a.title:
            print("No title: ", a.url)

        if not a.files:
            print("No files: ", a.url)

        a.info.pop('Reaction Emojis', None)

        a.save()


if __name__ == '__main__':
    cmt = Crawler()
    cmt.search(label="Concept Matrix Pose", sortby="time_posted", sortorder="desc", types=cmtool, nsfw=True)
    cmt.search(label="Concept Matrix Pose", sortby="time_posted", sortorder="desc", types=cmtool, nsfw=False)

    tex = Crawler()
    tex.search(label="Textools Mods", sortby="time_posted", sortorder="desc", types=textools, nsfw=True)
    tex.search(label="Textools Mods", sortby="time_posted", sortorder="desc", types=textools, nsfw=False)

    handle_document()

    for a in Archive.objects[:3]:
        pprint.pprint(a.to_mongo())
