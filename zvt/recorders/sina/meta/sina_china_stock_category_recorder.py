# -*- coding: utf-8 -*-
import json

import demjson
import pandas as pd
import requests

from zvt.contract.api import df_to_db
from zvt.contract.recorder import Recorder, TimeSeriesDataRecorder
from zvt.utils.time_utils import now_pd_timestamp
from zvt.api.quote import china_stock_code_to_id
from zvt.domain import BlockStock, BlockCategory, Block


class SwChinaBlockRecorder(Recorder):
    provider = 'sw'
    data_schema = Block

    url = 'http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodes'

    def run(self):
        resp = requests.get(self.url)
        resp_json = demjson.decode(resp.text)

        try:
            sw_blocks = resp_json[1][0][1][2][1]

            block_list = []
            for block_entry in sw_blocks:
                block_name = block_entry[0]
                sub_blocks = block_entry[1]
                for sub_block_entry in sub_blocks:
                    name = f'{block_name}_{sub_block_entry[0]}'
                    code = sub_block_entry[-1]
                    entity_id = f'block_cn_{code}'

                    block_list.append({
                        'id': entity_id,
                        'entity_id': entity_id,
                        'entity_type': 'block',
                        'exchange': 'cn',
                        'code': code,
                        'name': name,
                        'category': BlockCategory.industry.value
                    })

            if len(block_list) > 0:
                df = pd.DataFrame(block_list)
                df_to_db(data_schema=self.data_schema, df=df, provider=self.provider,
                         force_update=True)

            self.logger.info(f"finish record sw blocks...")

        except IndexError as error:
            self.logger.error("error: ,resp.text: ", error, resp.text)


class SinaChinaBlockRecorder(Recorder):
    provider = 'sina'
    data_schema = Block

    # 用于抓取行业/概念/地域列表
    category_map_url = {
        BlockCategory.industry: 'http://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php',
        BlockCategory.concept: 'http://money.finance.sina.com.cn/q/view/newFLJK.php?param=class'
        # StockCategory.area: 'http://money.finance.sina.com.cn/q/view/newFLJK.php?param=area',
    }

    def run(self):
        # get stock blocks from sina
        for category, url in self.category_map_url.items():
            resp = requests.get(url)
            resp.encoding = 'GBK'

            tmp_str = resp.text
            json_str = tmp_str[tmp_str.index('{'):tmp_str.index('}') + 1]
            tmp_json = json.loads(json_str)

            the_list = []

            for code in tmp_json:
                name = tmp_json[code].split(',')[1]
                entity_id = f'block_cn_{code}'
                the_list.append({
                    'id': entity_id,
                    'entity_id': entity_id,
                    'entity_type': 'block',
                    'exchange': 'cn',
                    'code': code,
                    'name': name,
                    'category': category.value
                })
            if the_list:
                df = pd.DataFrame.from_records(the_list)
                df_to_db(data_schema=self.data_schema, df=df, provider=self.provider,
                         force_update=True)

            self.logger.info(f"finish record sina blocks:{category.value}")


class SinaChinaBlockStockRecorder(TimeSeriesDataRecorder):
    entity_provider = 'sina'
    entity_schema = Block

    provider = 'sina'
    data_schema = BlockStock

    # 用于抓取行业包含的股票
    category_stocks_url = 'http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page={}&num=5000&sort=symbol&asc=1&node={}&symbol=&_s_r_a=page'

    def __init__(self, entity_type='block', exchanges=None, entity_ids=None, codes=None, batch_size=10,
                 force_update=True, sleeping_time=5, default_size=2000, real_time=False, fix_duplicate_way='add',
                 start_timestamp=None, end_timestamp=None, close_hour=0, close_minute=0) -> None:
        super().__init__(entity_type, exchanges, entity_ids, codes, batch_size, force_update, sleeping_time,
                         default_size, real_time, fix_duplicate_way, start_timestamp, end_timestamp, close_hour,
                         close_minute)

    def record(self, entity, start, end, size, timestamps):
        for page in range(1, 5):
            resp = requests.get(self.category_stocks_url.format(page, entity.code))
            try:
                if resp.text == 'null' or resp.text is None:
                    break
                category_jsons = demjson.decode(resp.text)
                the_list = []
                for category in category_jsons:
                    stock_code = category['code']
                    stock_id = china_stock_code_to_id(stock_code)
                    block_id = entity.id
                    the_list.append({
                        'id': '{}_{}'.format(block_id, stock_id),
                        'entity_id': block_id,
                        'entity_type': 'block',
                        'exchange': entity.exchange,
                        'code': entity.code,
                        'name': entity.name,
                        'timestamp': now_pd_timestamp(),
                        'stock_id': stock_id,
                        'stock_code': stock_code,
                        'stock_name': category['name'],

                    })
                if the_list:
                    df = pd.DataFrame.from_records(the_list)
                    df_to_db(data_schema=self.data_schema, df=df, provider=self.provider,
                             force_update=True)

                self.logger.info('finish recording BlockStock:{},{}'.format(entity.category, entity.name))

            except Exception as e:
                self.logger.error("error:,resp.text:", e, resp.text)
            self.sleep()


class SwChinaBlockStockRecorder(SinaChinaBlockStockRecorder):
    entity_provider = 'sw'
    entity_schema = Block

    provider = 'sina'
    data_schema = BlockStock


__all__ = ['SwChinaBlockRecorder', 'SwChinaBlockStockRecorder', 'SinaChinaBlockRecorder', 'SinaChinaBlockStockRecorder']

if __name__ == '__main__':
    # init_log('sina_china_stock_category.log')

    recorder = SinaChinaBlockStockRecorder(codes=['new_cbzz'])
    recorder.run()
