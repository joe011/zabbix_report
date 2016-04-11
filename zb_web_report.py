#!/usr/bin/python
#coding=utf8
import torndb
import datetime
import sys,os
from tornado import template

import time

reload(sys)
sys.setdefaultencoding("utf8")

db=torndb.Connection(host='localhost',user='zabbix',password='password',
					 database='zabbix',time_zone="+8:00", charset = "utf8",connect_timeout=60)

#两种类型，1种respone code，一种respone time

types={'respcode':0,'resptime':1}

#取7天的时间
now_time=datetime.date.today()
end_time=now_time - datetime.timedelta(days=1)
start_time=now_time - datetime.timedelta(days=7)

#根据httptestid查httptestname

httptestid_name=db.query("select httptestid,name from httptest; ")



#查询每个监控项对应的testid（项目分组使用）
def get_itemid_testid_name(types):
	sql="select  i.itemid ,s.httptestid,s.name from httpstep as s left join httpstepitem as i " \
		"on s.httpstepid=i.httpstepid and i.type=%s"
	ret=db.query(sql,types)
	return ret



def get_httptest_name(httptestid):
    for items in httptestid_name:
        if int(items['httptestid']) == httptestid:
            return items['name']


#查询每个监控项的响应状态码
def get_respcode_rate(itemid,start_time,end_time):
	sql="select IFNULL( value,  '1000' )  as status,count(value) as num  from history_uint" \
		" where itemid=%s AND from_unixtime(clock) between %s and %s  GROUP BY value WITH ROLLUP;"
	ret=db.query(sql,itemid,start_time,end_time)
	return ret



#查询每个监控项的响应时间
def get_resptime(itemid,start_time,end_time):
	sql='''select from_unixtime(clock,"%%Y-%%m-%%d") as date,itemid,value_max as time  from
trends where itemid=%s AND from_unixtime(clock) between %s and %s '''

	ret=db.query(sql,itemid,start_time,end_time)
	return ret


#查询所有监控项响应时间

def get_all_resptime(start_time,end_time):
	sql='''select count(*) as num, date,name,sum(time) as total_time from  (select
 			from_unixtime(t.clock,"%%Y-%%m-%%d") as date, t.itemid,p.name as name, t.value_max as time
 			 from trends as t inner join (httpstepitem as h,httpstep as s,httptest as p ) on
 			  ( h.httpstepid=s.httpstepid and  s.httpstepid=h.httpstepid and  s.httptestid=p.httptestid
 			  and t.itemid=h.itemid and h.type=1  and  from_unixtime(t.clock) between %s and %s )) as a group by date,name ;'''
	ret=db.query(sql,start_time,end_time)
	return ret



#各接口可用率
def generate_rate():
	service_items=get_itemid_testid_name(types['respcode'])
	data=[]
	for i in service_items:		
		t=get_respcode_rate(i['itemid'],start_time,end_time)
		ok=1
		pr=1
		ra={}
		for j in t:
			
			if int(j['status']) == 200:
				ok=int(j['num'])
			if int(j['status']) == 1000:
				pr=int(j['num'])
			ra["name"]=i['name']
			ra["testid"]=i['httptestid']
			ra["http_test_name"]=get_httptest_name(i['httptestid'])
			ra["rate"]='%.2f'%(float(ok)/pr*100)
			data.append(ra)
	return data


#各接口响应时间
def generate_time():
	service_items=get_itemid_testid_name(types['resptime'])
	data=[]
	for i in service_items:
		t=get_resptime(i['itemid'],start_time,end_time)

		for j in t:
			rt={}
			rt['datetime']=j['date']
			rt['name']=i['name']
			rt['testid']=get_httptest_name(i['httptestid'])
			rt['itemid']=j['itemid']
			rt['time']=j['time']


			data.append(rt)
	return data



#排序，计算
def zsorted(datas,kid,kvalue):
	counter_kv = {}
	results={}
	for i in datas:
		k = i[kid]

		if k not in counter_kv  :
			counter_kv[k] = {
				kvalue: 0.0,
				'count': 0

			}
		counter_kv[k][kvalue] += float(i[kvalue])
		counter_kv[k]['count'] += 1
		
	results = {m: '%.2f'%(float(n[kvalue])/n['count']) for m, n in counter_kv.iteritems()}
	return results


#生成html
def generate_graph(datas,names,t_times,p_times,datetimes,t_rates):
	loader = template.Loader("./templates")
	#可用率
	html = loader.load("index.html").generate(datas=datas,names=names,t_times=t_times,
					  p_times=p_times,datetimes=datetimes,t_rates=t_rates)
	return html





if __name__ == '__main__':
	# 各接口耗时统计
	t=generate_time()

	t_result=zsorted(t,'name','time')

	t_times=sorted(t_result.items(), key=lambda e:e[1], reverse=True)

	#各项目耗时统计

	p=get_all_resptime(start_time,end_time)
	grouptimes=sorted(p,key=lambda x:x['date'])
	datetimes=[]
	p_times={}
	for i in grouptimes:
		if i['date'] not in datetimes:
			datetimes.append(i['date'])

		if i['name'] not in p_times:
			p_times[i['name']]=[float('%.3f'%(float(i['total_time'])/int(i['num'])))*1000]
		else:
			p_times[i['name']].append(float('%.3f'%(float(i['total_time'])/int(i['num'])))*1000)

	#各项目可用率统计
	r=generate_rate()

	r_result=zsorted(r,'http_test_name','rate')
	t_sort=sorted(r_result.items(), key=lambda x:float(x[1]), reverse=False)

	#各接口可用率
	r_rates=zsorted(r,'name','rate')
	t_rates=sorted(r_rates.items(), key=lambda x:float(x[1]), reverse=False)



	names=[x[0] for x in t_sort]

	#生成html
	h_report=os.getcwdu()+'/htmls/'+str(end_time)+'.html'

	with open(h_report,'w') as f:
		f.write(generate_graph(enumerate(t_sort),names,t_times,p_times,datetimes,t_rates))
