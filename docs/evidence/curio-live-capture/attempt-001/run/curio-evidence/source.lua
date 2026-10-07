return {
name=[[Unclosed Square]],
inspect=function(ctx)
local s,i,c,st=ctx.sanity,ctx.insight,ctx.charges,ctx.state
if st==0 then
if i==0 then
return [[The tin is warm at three edges and cold at the fourth, which stops a hair short and holds a thin unfinished pitch.]]
elseif i<20 then
return [[The gap stays one hair short, yet it leans to a side this flat view cannot include.]]
else
return [[Edges disagree on which face is outer. The tin stays flat; only the count fails.]]
end
elseif st==1 then
if s>=70 then
return [[The break has slid one place along the rim. Same missing length; no longer where it was.]]
else
return [[Corners will not hold still: three, then four. The tin is cold and perfectly flat.]]
end
elseif c==0 then
return [[The square lies dull. The gap remains, a precise absence, and the metal gives no more.]]
elseif i==0 then
return [[Still only tin. The missing join has gone around the rim and has not closed.]]
else
return [[You can bound the square, not the way the break points. It offers no further side.]]
end
end,
apply=function(ctx)
local s,i,c,st=ctx.sanity,ctx.insight,ctx.charges,ctx.state
local ns,d,t=st,0,[[The tin square stays flat, its one gap unchanged.]]
if st==0 then
ns=1
if i==0 and s>=50 then
t=[[You set a thumb on the gap. The thin pitch stops short, and the break shifts one edge.]]
d=-1
elseif i==0 then
t=[[The flat tin steadies your count. Four corners, one gap. The unfinished pitch thins.]]
d=1
else
t=[[You try to include the missing side. The square stays flat and will not hold it.]]
if i>=50 then d=-2 else d=-1 end
end
elseif st==1 then
ns=2
if s>=40 then
t=[[The gap travels. Turning the square only repeats the same edge from a poorer angle.]]
if i>0 then d=-1 else d=0 end
else
t=[[You turn it and meet the same cold face. The count settles: a square, unfinished.]]
d=1
end
elseif st==2 then
ns=3
t=[[The break circles and does not close. A high thin sound dies at the same missing join.]]
if s<25 then d=1 elseif i>10 then d=-1 else d=0 end
elseif c==0 or st>=12 then
if ns>255 then ns=255 end
t=[[Nothing new yields. The rim is a closed line your hand cannot finish.]]
d=0
else
ns=st+1
if ns>255 then ns=255 end
t=[[The same join meets your thumb again, one place on, and still will not close.]]
if s<25 then d=1 elseif i>10 then d=-1 else d=0 end
end
if ns<0 then ns=0 elseif ns>255 then ns=255 end
if d<-2 then d=-2 elseif d>2 then d=2 end
return {text=t,state=ns,sanity_delta=d}
end
}