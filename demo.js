// ========== DATA ==========
var COLORS={华东:'#5b9cf6',华南:'#2dd4a0',西南:'#f5b731',华北:'#a78bfa'};
var AC=['#5b9cf6','#2dd4a0','#f5b731','#a78bfa','#fb923c','#f472b6','#c8956c','#93c5fd'];
var TAGS=[
  {id:'nature',name:'自然风光',cls:'t-nature'},{id:'culture',name:'人文历史',cls:'t-culture'},
  {id:'luxury',name:'奢享度假',cls:'t-luxury'},{id:'family',name:'亲子出行',cls:'t-family'},
  {id:'food',name:'美食体验',cls:'t-food'},{id:'hike',name:'户外徒步',cls:'t-hike'},
  {id:'photo',name:'摄影采风',cls:'t-photo'},{id:'snow',name:'雪山温泉',cls:'t-snow'}
];
var TCLR={nature:'#2dd4a0',culture:'#f5b731',luxury:'#e8b88a',family:'#5b9cf6',food:'#f472b6',hike:'#a78bfa',photo:'#fb923c',snow:'#93c5fd'};

var SALES={
  '华东':[
    {name:'杨慧中',total:352,linked:298,tagged:205,traded:72},
    {name:'陈丽华',total:318,linked:275,tagged:190,traded:68},
    {name:'张伟明',total:296,linked:240,tagged:168,traded:55},
    {name:'王静怡',total:284,linked:232,tagged:158,traded:51},
    {name:'刘佳琪',total:256,linked:210,tagged:145,traded:48},
    {name:'赵文轩',total:228,linked:186,tagged:128,traded:40}
  ],
  '华南':[
    {name:'屈婉祺',total:432,linked:356,tagged:245,traded:82},
    {name:'梁爱平',total:362,linked:298,tagged:210,traded:70},
    {name:'黄嘉伟',total:286,linked:235,tagged:162,traded:58},
    {name:'林美霞',total:248,linked:204,tagged:140,traded:45},
    {name:'吴志强',total:215,linked:178,tagged:122,traded:38}
  ],
  '西南':[
    {name:'张晓峰',total:380,linked:312,tagged:218,traded:78},
    {name:'和玉芳',total:345,linked:286,tagged:198,traded:65},
    {name:'次仁达娃',total:312,linked:258,tagged:178,traded:62},
    {name:'李春花',total:278,linked:228,tagged:156,traded:50},
    {name:'王建国',total:245,linked:202,tagged:138,traded:44},
    {name:'卓玛拉姆',total:198,linked:164,tagged:112,traded:38}
  ],
  '华北':[
    {name:'张曌依',total:804,linked:620,tagged:428,traded:142},
    {name:'李海燕',total:595,linked:488,tagged:336,traded:108},
    {name:'朱伯英',total:589,linked:475,tagged:328,traded:105},
    {name:'张嵩',total:587,linked:468,tagged:322,traded:110},
    {name:'刘雪梅',total:412,linked:338,tagged:232,traded:76},
    {name:'王志刚',total:356,linked:290,tagged:200,traded:64}
  ]
};

var REGIONS=Object.keys(SALES).map(function(r){
  var s=SALES[r],t=0,l=0,tg=0,td=0;
  s.forEach(function(x){t+=x.total;l+=x.linked;tg+=x.tagged;td+=x.traded});
  return{name:r,total:t,linked:l,linkedRate:+(l/t*100).toFixed(1),tagged:tg,taggedRate:+(tg/l*100).toFixed(1),traded:td,tradeRate:+(td/tg*100).toFixed(1)};
});

var RT={
  '华东':{nature:382,culture:268,luxury:312,family:225,food:186,hike:145,photo:168,snow:128},
  '华南':{nature:295,culture:215,luxury:248,family:198,food:225,hike:112,photo:132,snow:85},
  '西南':{nature:412,culture:298,luxury:186,family:165,food:198,hike:285,photo:268,snow:245},
  '华北':{nature:528,culture:412,luxury:386,family:325,food:268,hike:198,photo:186,snow:312}
};

var TT={nature:{total:1617,traded:485},culture:{total:1193,traded:392},luxury:{total:1132,traded:428},family:{total:913,traded:298},food:{total:877,traded:312},hike:{total:740,traded:268},photo:{total:754,traded:285},snow:{total:770,traded:295}};

function srand(s){return function(){s=Math.sin(s)*10000;return s-Math.floor(s)}}

var REGIONS_DEPT={
  '华东':['华东高客服务中心','会员管理'],
  '华南':['华南高客服务中心','会员管理'],
  '西南':['西南高客服务中心','会员管理'],
  '华北':['华北高客服务中心','会员管理']
};

function genCust(sn){
  var seed=0;for(var i=0;i<sn.length;i++)seed+=sn.charCodeAt(i);
  var rng=srand(seed),count=10+Math.floor(rng()*8);
  var s=['王','李','张','刘','陈','杨','黄','赵','周','吴','徐','孙','马','朱','胡','郭','林','何','高','罗'];
  var g=['伟','芳','娜','敏','静','丽','强','磊','洋','艳','勇','军','杰','涛','明','超','慧','志远','雅琴','雪梅','春华','文博','佳琪','思远','晓燕','海燕','美霞','嘉伟','婉祺'];
  var cs=[];
  for(var i=0;i<count;i++){
    var nm=s[Math.floor(rng()*s.length)]+g[Math.floor(rng()*g.length)]+(rng()>.5?g[Math.floor(rng()*g.length)]:'');
    var tc=1+Math.floor(rng()*3),tags=[],ids=TAGS.map(function(t){return t.id});
    for(var t=0;t<tc;t++){var id=ids[Math.floor(rng()*ids.length)];if(tags.indexOf(id)===-1)tags.push(id)}
    var lc=Math.floor(rng()*150),ht=lc<60&&rng()>.3,ta=ht?Math.floor(6000+rng()*45000):0;
    var fs=lc>60?'urgent':lc>30?'soon':'ok';
    var lv=ht?(ta>30000?'金刚':ta>15000?'莲':'雪莲'):(rng()>.7?'绿绒蒿':'格桑');
    var m=String(Math.floor(rng()*4)+1);if(m.length<2)m='0'+m;
    var d=String(Math.floor(rng()*28)+1);if(d.length<2)d='0'+d;
    var reg=rng()>.5?'华东':rng()>.5?'华南':rng()>.5?'西南':'华北';
    var depts=REGIONS_DEPT[reg],dept=depts[Math.floor(rng()*depts.length)];
    var mid='0000'+String(Math.floor(rng()*10000000000000));mid=mid.slice(-20);
    var cid='ST'+String(Math.floor(10000000000+rng()*90000000000));
    var wname=sn+'-'+nm;
    var y=2019+Math.floor(rng()*7);var mo=String(Math.floor(rng()*12)+1);if(mo.length<2)mo='0'+mo;
    var da=String(Math.floor(rng()*28)+1);if(da.length<2)da='0'+da;
    var regDate=y+'-'+mo+'-'+da;
    cs.push({name:nm,mid:mid,cid:cid,wname:wname,reg:reg,dept:dept,regDate:regDate,tags:tags,lc:lc,ht:ht,ta:ta,fs:fs,lv:lv,ltd:ht?('2026-'+m+'-'+d):'-'});
  }
  var fo={urgent:0,soon:1,ok:2};
  cs.sort(function(a,b){return fo[a.fs]-fo[b.fs]||b.ta-a.ta});
  return cs;
}

// ========== STATE ==========
var CV='overview',SR=null,SS=null,CH={},allC=[],cTF=null;

// ========== HELPERS ==========
function esc(s){return s.replace(/'/g,"\\'")}
function clr(rate,good,ok){return rate>good?'var(--green)':rate>ok?'var(--amber)':'var(--red)'}
function lr(s){return +(s.linked/s.total*100).toFixed(1)}
function trr(s){return +(s.traded/s.tagged*100).toFixed(1)}
function pr(s){return +(s.tagged/s.linked*100).toFixed(1)}
function kpi(label,val,sub,subc,vc){return '<div class="kpi"><div class="kpi-l">'+label+'</div><div class="kpi-v"'+(vc?' style="color:'+vc+'"':'')+'>'+val+'</div>'+(sub?'<div class="kpi-s '+(subc||'')+'">'+sub+'</div>':'')+'</div>';}
function rs(l,v){return '<div><div class="rg-sl">'+l+'</div><div class="rg-sv">'+v+'</div></div>';}

// ========== RENDER ==========
function render(){
  Object.values(CH).forEach(function(c){try{c.dispose()}catch(e){}});CH={};cTF=null;
  var app=document.getElementById('app');
  if(CV==='overview')app.innerHTML=rvO();
  else if(CV==='region')app.innerHTML=rvR();
  else app.innerHTML=rvS();
  uBC();
  requestAnimationFrame(function(){
    if(CV==='overview')iO();else if(CV==='region')iR();else iS();
  });
}

function uBC(){
  var bc=document.getElementById('bc'),h='<a onclick="goOverview()">全部大区</a>';
  if(CV!=='overview')h+=' <span class="sep">›</span> <a onclick="goRegion(\''+esc(SR)+'\')">'+SR+'</a>';
  if(CV==='sales')h+=' <span class="sep">›</span> <span>'+SS+'</span>';
  bc.innerHTML=h;
}

function goOverview(){CV='overview';SR=null;SS=null;render()}
function goRegion(r){CV='region';SR=r;SS=null;render()}
function goSales(r,s){CV='sales';SR=r;SS=s;render()}

// ========== OVERVIEW ==========
function rvO(){
  var tm=0,tl=0,tt=0,td=0;REGIONS.forEach(function(r){tm+=r.total;tl+=r.linked;tt+=r.tagged;td+=r.traded});
  var h='<div class="kpis fi">';
  h+=kpi('总会员数',tm.toLocaleString(),'↑ 2.1% 较上月','up');
  h+=kpi('建联率',(tl/tm*100).toFixed(1)+'%','↑ 0.3pp','up');
  h+=kpi('建联客户数',tl.toLocaleString(),'↑ 1.8%','up');
  h+=kpi('打标覆盖率',(tt/tl*100).toFixed(1)+'%','↓ 0.5pp','dn');
  h+=kpi('打标→交易转化',(td/tt*100).toFixed(1)+'%','↑ 1.2pp','up');
  h+='</div>';
  h+='<div class="sec fi"><div class="sec-h"><div class="sec-t">大区建联概览</div></div><div class="sec-b"><div class="rg-grid">';
  REGIONS.forEach(function(r){
    h+='<div class="rg-card" onclick="goRegion(\''+esc(r.name)+'\')">';
    h+='<div class="rg-name" style="color:'+COLORS[r.name]+'">'+r.name+'</div><div class="rg-stats">';
    h+=rs('会员总数',r.total.toLocaleString())+rs('建联客户',r.linked.toLocaleString());
    h+=rs('建联率',r.linkedRate+'%')+rs('打标→交易',r.tradeRate+'%');
    h+='</div><div class="rg-bar"><div class="rg-bar-f" style="width:'+r.linkedRate+'%;background:'+COLORS[r.name]+'"></div></div>';
    h+='<div style="margin-top:5px;font-size:10px;color:var(--text3)">点击查看销售员详情 ›</div></div>';
  });
  h+='</div></div></div>';
  h+='<div class="col2 fi">';
  h+='<div class="sec"><div class="sec-h"><div class="sec-t">各大区建联率对比</div></div><div class="sec-b"><div class="ch" id="c1"></div></div></div>';
  h+='<div class="sec"><div class="sec-h"><div class="sec-t">建联→打标→交易 漏斗</div></div><div class="sec-b"><div class="ch" id="c2"></div></div></div>';
  h+='</div>';
  h+='<div class="sec fi"><div class="sec-h"><div class="sec-t">客户标签打标与交易转化</div></div><div class="sec-b"><div class="ch" id="c3"></div></div></div>';
  return h;
}

function iO(){
  var c1=echarts.init(document.getElementById('c1'));CH.c1=c1;
  c1.setOption({tooltip:{trigger:'axis',backgroundColor:'#1b1f2c',borderColor:'#252a3a',textStyle:{color:'#e4e6eb',fontSize:12}},grid:{left:50,right:20,top:25,bottom:35},xAxis:{type:'category',data:REGIONS.map(function(r){return r.name}),axisLine:{lineStyle:{color:'#252a3a'}},axisLabel:{color:'#8b92a5'}},yAxis:{type:'value',axisLine:{show:false},splitLine:{lineStyle:{color:'#252a3a'}},axisLabel:{color:'#8b92a5',formatter:'{value}%'},max:25},series:[{type:'bar',barWidth:34,data:REGIONS.map(function(r){return{value:r.linkedRate,itemStyle:{color:COLORS[r.name]}}}),label:{show:true,position:'top',color:'#e4e6eb',fontSize:12,formatter:'{c}%'}}]});

  var tm=0,tl=0,tt=0,td=0;REGIONS.forEach(function(r){tm+=r.total;tl+=r.linked;tt+=r.tagged;td+=r.traded});
  var c2=echarts.init(document.getElementById('c2'));CH.c2=c2;
  c2.setOption({tooltip:{trigger:'item',backgroundColor:'#1b1f2c',borderColor:'#252a3a',textStyle:{color:'#e4e6eb'}},series:[{type:'funnel',left:'10%',top:15,bottom:15,width:'80%',min:0,max:tm,minSize:'0%',sort:'descending',gap:4,label:{show:true,position:'inside',color:'#fff',fontSize:12,formatter:function(p){return p.name+'\n'+p.value.toLocaleString()}},itemStyle:{borderColor:'#151821',borderWidth:2},data:[{value:tm,name:'总会员',itemStyle:{color:'#5c6378'}},{value:tl,name:'已建联',itemStyle:{color:'#5b9cf6'}},{value:tt,name:'已打标',itemStyle:{color:'#f5b731'}},{value:td,name:'已交易',itemStyle:{color:'#2dd4a0'}}]}]});

  var c3=echarts.init(document.getElementById('c3'));CH.c3=c3;
  c3.setOption({tooltip:{trigger:'axis',backgroundColor:'#1b1f2c',borderColor:'#252a3a',textStyle:{color:'#e4e6eb',fontSize:12}},legend:{data:['打标人数','交易人数','转化率'],textStyle:{color:'#8b92a5',fontSize:11},top:0},grid:{left:55,right:55,top:35,bottom:35},xAxis:{type:'category',data:TAGS.map(function(t){return t.name}),axisLine:{lineStyle:{color:'#252a3a'}},axisLabel:{color:'#8b92a5',fontSize:11}},yAxis:[{type:'value',axisLabel:{color:'#8b92a5'},splitLine:{lineStyle:{color:'#252a3a'}}},{type:'value',axisLabel:{color:'#8b92a5',formatter:'{value}%'},splitLine:{show:false},max:50}],series:[{name:'打标人数',type:'bar',barWidth:20,data:TAGS.map(function(t){return TT[t.id].total}),itemStyle:{color:'#5b9cf6',borderRadius:[3,3,0,0]}},{name:'交易人数',type:'bar',barWidth:20,data:TAGS.map(function(t){return TT[t.id].traded}),itemStyle:{color:'#2dd4a0',borderRadius:[3,3,0,0]}},{name:'转化率',type:'line',yAxisIndex:1,data:TAGS.map(function(t){return +(TT[t.id].traded/TT[t.id].total*100).toFixed(1)}),itemStyle:{color:'#f5b731'},lineStyle:{width:2},symbol:'circle',symbolSize:6}]});
}

// ========== REGION VIEW ==========
function rvR(){
  var r=REGIONS.find(function(x){return x.name===SR}),sales=SALES[SR];
  var h='<div style="margin-bottom:14px"><button class="bbtn" onclick="goOverview()">← 返回全部大区</button></div>';
  h+='<div class="kpis fi">';
  h+=kpi(SR+' · 会员总数',r.total.toLocaleString());
  h+=kpi('建联率',r.linkedRate+'%','','',COLORS[SR]);
  h+=kpi('建联客户',r.linked.toLocaleString());
  h+=kpi('打标覆盖率',r.taggedRate+'%');
  h+=kpi('打标→交易转化',r.tradeRate+'%');
  h+='</div>';

  h+='<div class="sec fi"><div class="sec-h"><div class="sec-t">销售员建联与转化</div></div><div class="sec-b"><div class="tw">';
  h+='<table><thead><tr><th>销售员</th><th>客户资产</th><th>建联客户</th><th>建联率</th><th>已打标</th><th>打标率</th><th>已交易</th><th>转化率</th><th>建联率</th><th></th></tr></thead><tbody>';
  sales.forEach(function(s,i){
    var r1=lr(s),r2=pr(s),r3=trr(s);
    h+='<tr class="ck" onclick="goSales(\''+esc(SR)+'\',\''+esc(s.name)+'\')">';
    h+='<td><div class="sale-name"><div class="sale-av" style="background:'+AC[i%8]+'">'+s.name[0]+'</div>'+s.name+'</div></td>';
    h+='<td>'+s.total.toLocaleString()+'</td><td>'+s.linked.toLocaleString()+'</td><td style="color:'+clr(r1,75,60)+'">'+r1+'%</td>';
    h+='<td>'+s.tagged.toLocaleString()+'</td><td>'+r2+'%</td><td>'+s.traded.toLocaleString()+'</td><td style="color:'+clr(r3,35,30)+'">'+r3+'%</td>';
    h+='<td><div class="mbar"><div class="mbar-track"><div class="mbar-fill" style="width:'+r1+'%;background:'+clr(r1,75,60)+'"></div></div></div></td>';
    h+='<td style="color:var(--gold);font-size:11px">详情 ›</td></tr>';
  });
  h+='</tbody></table></div></div></div>';

  h+='<div class="col2 fi">';
  h+='<div class="sec"><div class="sec-h"><div class="sec-t">销售员建联率排名</div></div><div class="sec-b"><div class="ch" id="c4"></div></div></div>';
  h+='<div class="sec"><div class="sec-h"><div class="sec-t">'+SR+' 标签打标分布</div></div><div class="sec-b"><div class="ch" id="c5"></div></div></div>';
  h+='</div>';
  h+='<div class="sec fi"><div class="sec-h"><div class="sec-t">标签打标→交易转化（'+SR+'）</div></div><div class="sec-b"><div class="ch" id="c6"></div></div></div>';
  return h;
}

function iR(){
  var sales=SALES[SR],color=COLORS[SR];
  var sorted=sales.slice().sort(function(a,b){return(b.linked/b.total)-(a.linked/a.total)});
  var c4=echarts.init(document.getElementById('c4'));CH.c4=c4;
  c4.setOption({tooltip:{trigger:'axis',backgroundColor:'#1b1f2c',borderColor:'#252a3a',textStyle:{color:'#e4e6eb',fontSize:12}},grid:{left:75,right:20,top:8,bottom:25},xAxis:{type:'value',axisLabel:{color:'#8b92a5',formatter:'{value}%'},splitLine:{lineStyle:{color:'#252a3a'}},max:100},yAxis:{type:'category',data:sorted.map(function(s){return s.name}).reverse(),axisLine:{lineStyle:{color:'#252a3a'}},axisLabel:{color:'#8b92a5',fontSize:12}},series:[{type:'bar',barWidth:16,data:sorted.map(function(s){var v=lr(s);return{value:v,itemStyle:{color:v>75?'#2dd4a0':v>60?'#f5b731':'#f04444',borderRadius:[0,3,3,0]}}}).reverse(),label:{show:true,position:'right',color:'#e4e6eb',fontSize:11,formatter:'{c}%'}}]});

  var c5=echarts.init(document.getElementById('c5'));CH.c5=c5;
  var rt=RT[SR];
  c5.setOption({tooltip:{trigger:'item',backgroundColor:'#1b1f2c',borderColor:'#252a3a',textStyle:{color:'#e4e6eb'}},legend:{orient:'vertical',right:8,top:'center',textStyle:{color:'#8b92a5',fontSize:11}},series:[{type:'pie',radius:['38%','68%'],center:['38%','50%'],label:{color:'#8b92a5',fontSize:11},data:TAGS.map(function(t){return{name:t.name,value:rt[t.id],itemStyle:{color:TCLR[t.id]}}})}]});

  var c6=echarts.init(document.getElementById('c6'));CH.c6=c6;
  var rng=srand(SR.charCodeAt(0)+SR.charCodeAt(1));
  var rd=TAGS.map(function(t){var b=TT[t.id],ratio=rt[t.id]/b.total;var traded=Math.round(b.traded*ratio*(0.8+rng()*0.4));return{name:t.name,tagged:rt[t.id],traded:traded,rate:+(traded/rt[t.id]*100).toFixed(1)}});
  c6.setOption({tooltip:{trigger:'axis',backgroundColor:'#1b1f2c',borderColor:'#252a3a',textStyle:{color:'#e4e6eb',fontSize:12}},legend:{data:['打标人数','交易人数','转化率'],textStyle:{color:'#8b92a5',fontSize:11},top:0},grid:{left:55,right:55,top:35,bottom:35},xAxis:{type:'category',data:rd.map(function(d){return d.name}),axisLine:{lineStyle:{color:'#252a3a'}},axisLabel:{color:'#8b92a5',fontSize:11}},yAxis:[{type:'value',axisLabel:{color:'#8b92a5'},splitLine:{lineStyle:{color:'#252a3a'}}},{type:'value',axisLabel:{color:'#8b92a5',formatter:'{value}%'},splitLine:{show:false},max:60}],series:[{name:'打标人数',type:'bar',barWidth:20,data:rd.map(function(d){return d.tagged}),itemStyle:{color:color,borderRadius:[3,3,0,0]}},{name:'交易人数',type:'bar',barWidth:20,data:rd.map(function(d){return d.traded}),itemStyle:{color:'#2dd4a0',borderRadius:[3,3,0,0]}},{name:'转化率',type:'line',yAxisIndex:1,data:rd.map(function(d){return d.rate}),itemStyle:{color:'#f5b731'},lineStyle:{width:2},symbol:'circle',symbolSize:6}]});
}

// ========== SALES VIEW ==========
function rvS(){
  var s=SALES[SR].find(function(x){return x.name===SS});
  allC=genCust(SS);
  var urgent=allC.filter(function(c){return c.fs==='urgent'}).length;
  var soon=allC.filter(function(c){return c.fs==='soon'}).length;
  var traded=allC.filter(function(c){return c.ht});
  var totalT=traded.reduce(function(a,c){return a+c.ta},0);
  var r1=lr(s),r2=pr(s),r3=trr(s);

  var h='<div style="margin-bottom:14px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">';
  h+='<button class="bbtn" onclick="goRegion(\''+esc(SR)+'\')">← 返回'+SR+'</button>';
  h+='<span style="color:var(--text2);font-size:12px">'+SS+' 的客户资产</span></div>';

  h+='<div class="kpis fi">';
  h+=kpi('客户资产',s.total.toLocaleString());
  h+=kpi('建联客户',s.linked.toLocaleString(),'建联率 '+r1+'%');
  h+=kpi('已打标',s.tagged.toLocaleString(),'覆盖率 '+r2+'%');
  h+=kpi('已交易',s.traded.toLocaleString(),'转化率 '+r3+'%');
  h+=kpi('交易金额','¥'+(totalT/10000).toFixed(1)+'万');
  h+='</div>';

  if(urgent>0||soon>0){
    h+='<div class="urg-panel fi"><span style="font-size:18px">🚨</span><div class="urg-text">需立即跟进 <span class="urg-num">'+urgent+'</span> 人，即将到期 <span class="urg-num">'+soon+'</span> 人</div></div>';
  }

  h+='<div class="sec fi"><div class="sec-h"><div class="sec-t">客户标签概况</div></div><div class="sec-b"><div class="ch ch-sm" id="c7"></div></div></div>';

  h+='<div class="sec fi"><div class="sec-h"><div class="sec-t">客户跟进清单</div>';
  h+='<div class="tag-filter" id="tf">';
  h+='<button class="tf-btn on" onclick="filterTag(null)">全部</button>';
  TAGS.forEach(function(t){h+='<button class="tf-btn" onclick="filterTag(\''+t.id+'\')">'+t.name+'</button>'});
  h+='</div></div><div class="sec-b"><div class="tw">';
  h+='<table><thead><tr><th>跟进状态</th><th>等级</th><th>客户姓名</th><th>会员ID</th><th>会员卡号</th><th>企微建联名称</th><th>会员区域</th><th>企微添加部门</th><th>标签</th><th>最近联系</th><th>消费金额</th><th>最近下单</th></tr></thead>';
  h+='<tbody id="cb">'+renderCustRows(allC)+'</tbody></table></div></div></div>';
  return h;
}

function renderCustRows(list){
  var h='';
  list.forEach(function(c){
    var cc=c.fs==='urgent'?'cust-urg':c.fs==='soon'?'cust-soon':'';
    var fb=c.fs==='urgent'?'<span class="fb fb-urg">🔴 需跟进</span>':c.fs==='soon'?'<span class="fb fb-spn">🟡 即将到期</span>':'<span class="fb fb-ok">🟢 正常</span>';
    var tags='';c.tags.forEach(function(tid){var t=TAGS.find(function(x){return x.id===tid});if(t)tags+='<span class="tag '+t.cls+'">'+t.name+'</span>';});
    h+='<tr class="'+cc+'">';
    h+='<td>'+fb+'</td>';
    h+='<td><span class="lvl lvl-'+c.lv+'">'+c.lv+'</span></td>';
    h+='<td><div style="font-weight:500">'+c.name+'</div><div style="font-size:10px;color:var(--text3)">注册:'+c.regDate+'</div></td>';
    h+='<td style="color:var(--text2);font-size:11px">'+c.mid+'</td>';
    h+='<td style="color:var(--text2);font-size:11px">'+c.cid+'</td>';
    h+='<td><div style="color:var(--blue)">'+c.wname+'</div></td>';
    h+='<td style="font-size:12px">'+c.reg+'</td>';
    h+='<td style="font-size:11px;color:var(--text2)">'+c.dept+'</td>';
    h+='<td>'+tags+'</td>';
    h+='<td style="color:'+(c.lc>60?'var(--red)':c.lc>30?'var(--amber)':'var(--text)')+'">'+c.lc+'天前</td>';
    h+='<td'+(c.ta>0?' style="color:var(--green);font-weight:600"':'')+'>'+(c.ta>0?'¥'+c.ta.toLocaleString():'-')+'</td>';
    h+='<td>'+c.ltd+'</td></tr>';
  });
  return h;
}

function iS(){
  var c7=echarts.init(document.getElementById('c7'));CH.c7=c7;
  var tagMap={};TAGS.forEach(function(t){tagMap[t.id]={name:t.name,count:0,traded:0}});
  allC.forEach(function(c){c.tags.forEach(function(tid){if(tagMap[tid]){tagMap[tid].count++;if(c.ht)tagMap[tid].traded++}})});
  c7.setOption({tooltip:{trigger:'axis',backgroundColor:'#1b1f2c',borderColor:'#252a3a',textStyle:{color:'#e4e6eb',fontSize:12}},legend:{data:['打标客户','已交易','转化率'],textStyle:{color:'#8b92a5',fontSize:11},top:0},grid:{left:50,right:50,top:35,bottom:25},xAxis:{type:'category',data:TAGS.map(function(t){return t.name}),axisLine:{lineStyle:{color:'#252a3a'}},axisLabel:{color:'#8b92a5',fontSize:11}},yAxis:[{type:'value',axisLabel:{color:'#8b92a5'},splitLine:{lineStyle:{color:'#252a3a'}}},{type:'value',axisLabel:{color:'#8b92a5',formatter:'{value}%'},splitLine:{show:false},max:100}],series:[{name:'打标客户',type:'bar',barWidth:20,data:TAGS.map(function(t){return tagMap[t.id].count}),itemStyle:{color:'#5b9cf6',borderRadius:[3,3,0,0]}},{name:'已交易',type:'bar',barWidth:20,data:TAGS.map(function(t){return tagMap[t.id].traded}),itemStyle:{color:'#2dd4a0',borderRadius:[3,3,0,0]}},{name:'转化率',type:'line',yAxisIndex:1,data:TAGS.map(function(t){return tagMap[t.id].count>0?+(tagMap[t.id].traded/tagMap[t.id].count*100).toFixed(1):0}),itemStyle:{color:'#f5b731'},lineStyle:{width:2},symbol:'circle',symbolSize:6}]});
}

function filterTag(tid){
  cTF=tid;
  var btns=document.querySelectorAll('.tf-btn');
  btns.forEach(function(b){b.classList.remove('on')});
  if(!tid)btns[0].classList.add('on');
  else{
    btns[0].classList.remove('on');
    btns.forEach(function(b){if(b.textContent===TAGS.find(function(t){return t.id===tid}).name)b.classList.add('on')});
  }
  var filtered=tid?allC.filter(function(c){return c.tags.indexOf(tid)!==-1}):allC;
  document.getElementById('cb').innerHTML=renderCustRows(filtered);
}

render();

window.addEventListener('resize',function(){
  Object.values(CH).forEach(function(c){try{c.resize()}catch(e){}});
});