# -*- coding: utf-8 -*-
"""
Created at: 17-12-22 上午11:03

@Author: Qian
"""

import re
import os
import json
import time
import queue
import random
import pymysql
import logging
import datetime
import requests
import threading
from bs4 import BeautifulSoup
from my_modules import mysqlconn
from jinja2 import Environment, FileSystemLoader

################################################################################
# 日志
logger = logging.getLogger("Amazon Competitor Monitor")
logger.setLevel(logging.DEBUG)
# 日志格式
fmt = logging.Formatter('[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S')
# 文件日志, DEBUG级别
fh = logging.FileHandler(os.path.join(os.path.dirname(__file__), 'Amazon.log'))
fh.setLevel(logging.DEBUG)
fh.setFormatter(fmt)
# 控制台日志, DEBUG级别
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
ch.setFormatter(fmt)
# 将相应的handler添加在logger对象中
logger.addHandler(fh)
logger.addHandler(ch)

###############################################################################
# 全局变量
project_dir = os.path.dirname(__file__)
with open(os.path.join(project_dir, "asin.txt")) as f:
    asin_list = list(set(eval(f.readlines()[0])))
invalid_asin_list = []
urls_queue = queue.Queue()
pages_queue = queue.Queue()
lock = threading.Lock()
urls_exit_flag = 0
pages_exit_flag = 0
db_config = {"db": "DB_NAME"}
headers = {"Host": "www.amazon.com",
           "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:57.0) Gecko/20100101 Firefox/57.0",
           "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
           "Accept-Language": "zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2",
           "Accept-Encoding": "gzip, deflate, br",
           "Connection": "keep-alive",
           "Upgrade-Insecure-Requests": "1"}


##############################################################################
# request线程
class RequestThread(threading.Thread):
    """获取网页的线程，负责发起请求"""

    def __init__(self, thread_id):
        super(RequestThread, self).__init__()
        self.threadID = thread_id
        self.name = "request_thread"

    def run(self):
        """从urls_queue队列中取出url，发送请求，将返回的page放入pages_queue"""

        while not urls_exit_flag:
            result = {}
            lock.acquire()
            if not urls_queue.empty():
                url, state, failure_times, headers, proxies, error_num = urls_queue.get()
                lock.release()
                result["url"] = url
                result["asin"] = url.split("=")[-1]
                result["headers"] = headers
                result["proxies"] = proxies
                try:
                    page = requests.get(url, headers=headers, proxies=proxies, timeout=10)
                except Exception as e:
                    result["state"] = e
                    result["failure_times"] = failure_times + 1
                    result["error_num"] = error_num + 1
                    logger.error("Failed   " + result['asin'])
                    self.fail_function(result)
                else:
                    if page.status_code != 200:
                        result["state"] = Exception("Page's status code is" + str(page.status_code))
                        result["failure_times"] = failure_times + 1
                        result["error_num"] = error_num + 1
                        logger.error("Failed(proxy_error)   " + result['asin'] + "   " + str(result['proxies']))
                        self.fail_function(result)
                    else:
                        pages_queue.put((url, "success", page, result["asin"]))
                        logger.info("Success   " + result['asin'])
                        # print(proxies, url, "success")
            else:
                lock.release()
                time.sleep(1)

    @staticmethod
    def fail_function(result=None):
        """请求失败后的处理
        更新ip_proxy数据库，重新获取proxies，将url再次加入到urls_queue中"""

        if result:
            # print(result["state"])
            url = result["url"]
            RequestThread.proxy_fail(result["proxies"], result["error_num"])
            proxies, error_num = RequestThread.get_proxy()
            state = "outstanding"
            failure_times = result["failure_times"] + 1
            urls_queue.put((url, state, failure_times, headers, proxies, error_num))

    @staticmethod
    def proxy_fail(proxies, error_num):
        """代理失败，将数据库中该ip代理的error_num加1"""

        if proxies:
            # 从proxies中将ip和port提取出来
            _, ip, port = proxies["https"].split(":")
            ip = ip[2:]
            sql_string = "update ip_proxy set error_num=%i where ip='%s' and port='%s'" % (error_num, ip, port)
            conn = mysqlconn.mysqlconn(**db_config)
            cur = conn.cursor()
            try:
                cur.execute(sql_string)
                conn.commit()
            except Exception as e:
                conn.rollback()
                conn.close()
                raise e
            conn.close()
        else:
            pass

    @staticmethod
    def get_proxy(ip_list=None):
        """从数据库中获取代理ip并随机选取一个代理"""

        # 如果没有传入ip_list，则从数据库中取出
        if not ip_list:
            conn = mysqlconn.mysqlconn(**db_config)
            cur = conn.cursor()
            cur.execute("select * from ip_proxy where https='yes' and error_num<6 and state<>'dead'")
            ip_list = cur.fetchall()
            conn.close()

        if ip_list == "None":
            return None, 0

        proxy = random.choice(ip_list)
        proxies = {"https": "http://" + proxy[0] + ":" + proxy[1]}
        return proxies, proxy[3]


##############################################################################
# 页面解析线程
class AmazonProduct(threading.Thread):
    """分析页面的线程，负责解析页面源代码，获取数据并存入数据库"""

    count = 0  # 产品页面解析 计数，用以作判断线程退出的条件

    def __init__(self, thread_id):
        super(AmazonProduct, self).__init__()
        self.threadID = thread_id
        self.name = "parse_thread"
        self.result = {}
        self.__parse_string = {
            'title': '<h2 .*?>(.*?)</h2>',
            'price': '<span class="a-offscreen">(.*?)</span>',
            'star': '<i class="a-icon a-icon-star .*?>.*?<span class="a-icon-alt">(.*?)</span>.*?</i>',
            'review_num': '<a .*?#customerReviews">(.*?)</a>',
            'listing_url': '<a class="a-link-normal s-access-detail-page .*? href="(.*?)">',
        }

    def run(self):
        while not pages_exit_flag:
            lock.acquire()
            if not pages_queue.empty():
                url, state, page, asin = pages_queue.get()
                lock.release()
                self.result = {}
                self.parse_page(url, page, asin)
                self.db_insert()
            else:
                lock.release()
                time.sleep(1)

    def parse_page(self, url, page, asin):
        """有两种页面需要解析，一种是搜索页面，一种是产品页面。可根据url判断页面类型。"""

        if url.startswith("https://www.amazon.com/s/ref=nb_sb_noss"):
            url = self.parse_1(page, asin)
            if url:
                proxies, error_num = RequestThread.get_proxy()
                lock.acquire()
                urls_queue.put((url, "outstanding", 0, headers, proxies, error_num))
                lock.release()
        else:
            self.parse_2(page, asin)

        print(self.result)

    def parse_1(self, page, asin):
        """解析搜索页面"""

        self.result["asin"] = asin
        # 取出结果部分
        try:
            string = '<li id="result_0" .*?>(.*?)</li>'
            pattern = re.compile(string)
            page = re.findall(pattern, page.text.replace('\n', ''))[0]
        except:
            self.result['error'] = "No that product"
            logger.error("No that part(product)   " + self.result['asin'])
            AmazonProduct.count += 1
            handle_invalid_asin(self.result["asin"])
            return 0
        # 提取title
        self.__parse_text(page, 'title')
        # 提取price
        self.__parse_text(page, 'price')
        # 提取评分(star)
        self.__parse_text(page, 'star')
        # 提取review_num
        self.__parse_text(page, 'review_num')
        # 提取listing_url
        self.__parse_text(page, 'listing_url')
        if self.result['listing_url']:
            url = self.result['listing_url'].replace("&amp;", "&")
            return url
        else:
            logger.error(self.result['asin'] + "   No listing url")
            AmazonProduct.count += 1
            return 0

    def __parse_text(self, text, info_type):
        # 提取text中关于info_type的信息
        try:
            string = self.__parse_string[info_type]
            pattern = re.compile(string)
            self.result[info_type] = re.findall(pattern, text)[0]
            return 1
        except IndexError:
            self.result[info_type] = 'NULL'
            logger.error("No " + info_type + "   " + self.result['asin'])
            return 0

    def parse_2(self, page, asin):
        """解析产品页面,获取排名和产品图片地址"""

        self.result["asin"] = asin
        soup = BeautifulSoup(page.text, "lxml")

        # 取出包含rank的table部分
        try:
            rank_info = soup.find_all("table", id="productDetails_detailBullets_sections1")[0]
            self.__parse_rank_info(rank_info)
        except:
            logger.error("No Rank Info Part")

        # 取出Product description部分
        try:
            product_description = soup.find_all("div", id="dpx-product-description_feature_div")
            self.__parse_description(product_description)
        except:
            logger.error("No Product Description Part")

        # 取出包含image url的部分
        try:
            scripts = soup.find_all("script", type="text/javascript")
            flag = True
            while flag:
                for script in scripts:
                    if "P.when('A').register" in script.text:
                        flag = False
                        break
                if flag:
                    raise Exception("Not Finding Image Url Part")
            string = "var data = ({.*?});.*?return data;"
            pattern = re.compile(string)
            img_info = re.findall(pattern, script.text.replace("\n", ""))[0]
            self.__parse_img_url(img_info)
        except:
            logger.error("No Image Url Part")

        AmazonProduct.count += 1

    def __parse_rank_info(self, soup):
        rank = []

        trs = soup.find_all("tr")
        rank_tr = BeautifulSoup('', "lxml")
        for tr in trs:
            # 找出Best Sellers Rank那一行
            if "Best Sellers Rank" in tr.text:
                rank_tr = tr
                break
        for r in rank_tr.text.split("\n"):
            if r.startswith("#"):
                rank.append(r)
                # print(r)
                # r 应该会如下这样的形式：
                #   #21 in Electronics > Headphones > Over-Ear Headphones
        self.result["rank"] = rank

    def __parse_description(self, text):
        pass

    def __parse_img_url(self, text):
        img_urls = []

        try:
            # 解析出图片地址
            img_info = json.loads(text.replace("\'", '"'))
            for i in img_info["colorImages"]["initial"]:
                # print(i["hiRes"])
                img_urls.append(i["large"])
        except:
            pass

        self.result["img_urls"] = img_urls

    def db_insert(self):
        if self.result.get('error'):
            return 0

        self.__format_result()

        try:
            conn = mysqlconn.mysqlconn(**db_config)
            mysqlconn.db_insert(conn, self.result, 'product_info')
        except pymysql.err.IntegrityError:
            mysqlconn.db_update(conn, self.result, ['asin', 'last_update_time'], 'product_info')
        except:
            logger.exception(self.result['asin'] + '   db_insert error')
        finally:
            conn.close()

    def __format_result(self):
        # 先对数据做一些处理后再存入数据库
        self.result['last_update_time'] = time.strftime("%Y-%m-%d %H:00:00")

        if self.result.get('price'):
            self.result.pop('listing_url')
            if self.result['price'] != 'NULL':
                self.result['currency_code'] = self.result['price'][0]
                self.result['price'] = float(self.result['price'][1:])

        if self.result.get('img_urls'):
            img_urls = self.result.pop('img_urls')
            if img_urls:
                for i in range(len(img_urls)):
                    self.result['img' + str(i + 1)] = img_urls[i]
            else:
                self.result['img1'] = 'NULL'

            rank = self.result.pop('rank')
            if rank:
                for i in range(len(rank)):
                    self.result['rank' + str(i + 1)] = rank[i]
            else:
                self.result['rank1'] = 'NULL'


##############################################################################
# 处理无效asin
def handle_invalid_asin(invalid_asin):
    logger.info("Handle Invalid ASIN: " + invalid_asin)
    if invalid_asin in asin_list:
        lock.acquire()
        asin_list.remove(invalid_asin)
        invalid_asin_list.append(invalid_asin)
        lock.release()
        logger.info("Complete Handle Invalid ASIN: " + invalid_asin)
    else:
        logger.info(invalid_asin + " Already not in asin_list")

# 保存asin_list和invalid_asin_list:
def store_asin():
    with open(os.path.join(project_dir, "asin.txt"), 'w') as f:
        f.writelines(str(asin_list))

    with open(os.path.join(project_dir, "asin_invalid.txt"), 'r') as f:
        stored_invalid_asin = list(set(eval(f.readlines()[0])))
    for i in invalid_asin_list:
        if i not in stored_invalid_asin:
            stored_invalid_asin.append(i)
    with open(os.path.join(project_dir, "asin_invalid.txt"), 'w') as f:
        f.writelines(str(stored_invalid_asin))


#创建urls_queue
def create_urls_queue(asin_list):
    """创建urls_queue"""

    global urls_queue
    # 依据asin_list创建urls_list
    urls_list = []
    for asin in asin_list:
        url = "https://www.amazon.com/s/ref=nb_sb_noss?url=search-alias%3Daps&field-keywords=" + asin
        urls_list.append(url)

    # 从数据库获取代理ip
    conn = mysqlconn.mysqlconn(**db_config)
    cur = conn.cursor()
    cur.execute("select * from ip_proxy where https='yes' and error_num<6 and state<>'dead'")
    ip_list = cur.fetchall()
    conn.close()

    for i in urls_list:
        proxies, error_num = RequestThread.get_proxy(ip_list)
        urls_queue.put((i, "outstanding", 0, headers, proxies, error_num))


##############################################################################
# 监控数据库信息变化

# 用作储存产品信息变化的容器
class Changing:
    """"""

    def __init__(self):
        self.asin_list = []
        self.difference = []

    # 处理rank变化
    def format_rank_diff(self):
        if not self.difference:
            return 0
        pass


# 从数据库中获取每个asin最新的两条记录
def get_latest_data():
    """
    从数据库中获取每个asin最新的两条记录
    :return: dict型数据
    """

    # 取出每个asin最新的两条记录
    sql = "select a.* from product_info as a where 2>(" \
          "select count(*) from product_info where asin=a.asin and last_update_time>a.last_update_time" \
          ") order by a.asin,a.last_update_time;"
    conn = mysqlconn.mysqlconn(**db_config)
    cur = conn.cursor()
    cur.execute(sql)
    # data变量每个位置的数据意义,如下
    # ['asin', 'last_update_time', 'title', 'price', 'currency_code', 'review_num', 'star', 'img1', 'img2', 'img3', 'img4', 'img5', 'img6', 'img7', 'img8', 'img9', 'img0', 'rank1', 'rank2', 'rank3', 'rank4', 'rank0', ]
    data = cur.fetchall()
    conn.close()
    data = _format_data(data)
    return data


# 格式化数据,将同一asin的数据放在一起,以方便后续进行比较
def _format_data(data, now=True):
    """
    格式化数据,将同一asin的数据放在一起,以方便后续进行比较
    :param data: 从数据库取出的原始数据
    :param now: 是否要求最新的记录为当前时间的记录, 默认为True
    :return: dict型数据, 如{'asin':[[...], [...]]}
    """

    d = {}

    for i in data:
        if i[0] in d:
            d[i[0]].append([j for j in i])
        else:
            d[i[0]] = [[j for j in i], ]

    # 删除只有一条记录的数据
    asin_list = list(d.keys())
    for asin in asin_list:
        if len(d[asin]) < 2:
            d.pop(asin)
            continue
        # html字符替换
        d[asin][0][2] = _char_sub(d[asin][0][2])
        d[asin][1][2] = _char_sub(d[asin][1][2])

    # 删除没有新纪录的数据
    if now:
        now = datetime.datetime.now().replace(minute=0, second=0, microsecond=0)
        # now = datetime.datetime.strptime("2018-01-24 02:00:00", "%Y-%m-%d %H:%M:%S")
        asin_list = list(d.keys())
        for asin in asin_list:
            if (d[asin][0][1] != now) and (d[asin][1][1] != now):
                d.pop(asin)

    return d


# 将title中特殊的html字符替换成正常字符
def _char_sub(string):
    char = {"&#39;": "'",
            '&quot;': '"',
            "&amp;": "&", }
    for i in char:
        string = string.replace(i, char[i])
    return string


# 检测最新的两条记录中是否有信息发生改变
def check_change(data):
    change = Changing()
    columns = ['asin', 'last_update_time', 'title', 'price', 'currency_code', 'review_num', 'star',
               'img1', 'img2', 'img3', 'img4', 'img5', 'img6', 'img7', 'img8', 'img9', 'img0',
               'rank1', 'rank2', 'rank3', 'rank4', 'rank0', ]

    for asin in data:
        for i in range(2, len(data[asin][0])):
            if data[asin][0][i] != data[asin][1][i]:
                change.asin_list.append(asin)
                change.difference.append({'asin': asin, 'key': columns[i],
                                          'before': data[asin][0][i],
                                          'now': data[asin][1][i]})

    return change


# 获取html字符串
def get_html(change, invalid_asin=None):
    env = Environment(loader=FileSystemLoader(os.path.dirname(__file__), 'utf-8'))
    t = env.get_template("mail_template.html")
    html = t.render(difference=change.difference, invalid_asin=invalid_asin)
    return html


##############################################################################
# 发送e-mail
MAIL = {
    "test": {
        "to": [
            "abc@123.com",
        ],

        "cc": [
            "def@456.com",
        ],
    },
}
def send_mail(account, subject, text=None, html=None, files=None):
    mail_box = MAIL[account]
    data = {
        "from": "abc@123.com",
        "to": mail_box['to'],
        "cc": mail_box['cc'],
        "subject": subject,
        "text": text,
        "html": html,
    }

    if not text:
        data.pop("text")
    if not html:
        data.pop("html")
    if files:
        r = requests.post(
            "https://api.mailgun.net/XXXXXX",
            auth=("api", "key-123456789"),
            files=files,
            data=data
        )
    else:
        r = requests.post(
            "https://api.mailgun.net/XXXXXX",
            auth=("api", "key-123456789"),
            data=data
        )
    return r


##############################################################################
# 主程序
if __name__ == "__main__":
    # crawler part
    logger.info('Crawler Start')

    create_urls_queue(asin_list)

    threads = []
    max_threads_num = 8
    threads_num = min(urls_queue.qsize(), max_threads_num)

    logger.info('Creating Threads')
    for i in range(threads_num):
        logger.info("RequestThread-" + str(i))
        thread = RequestThread(i)
        thread.setDaemon(True)
        logger.info("RequestThread-" + str(i) + " Start")
        thread.start()
        threads.append(thread)
    logger.info("AmazonProduct Thread")
    thread = AmazonProduct(threads_num+1)
    thread.setDaemon(True)
    logger.info("AmazonProduct Thread" + " Start")
    thread.start()
    threads.append(thread)

    # 当所有产品都解析完成的时候，join所有线程
    while AmazonProduct.count < len(asin_list):
        time.sleep(1)
        pass
    pages_exit_flag = 1
    urls_exit_flag = 1
    for i in range(threads_num+1):
        threads[i].join()
    logger.info('All Threads joined')

    # store_asin()
    logger.info('Crawler End')

    #################################################
    # monitor part
    logger.info('Monitor Start')
    logger.info('Get data from database')
    data = get_latest_data()
    logger.info('Check the change')
    change = check_change(data)
    if change.asin_list or invalid_asin_list:
        logger.info('Get html string')
        html = get_html(change, invalid_asin=invalid_asin_list)
        logger.info('Send E-mail')
        subject = time.strftime("%Y-%m-%d") + " Competitor Monitor"
        # r = send_mail('test', subject, html=html)
    logger.info('Monitor End')

    logger.info('All End')
    pass
