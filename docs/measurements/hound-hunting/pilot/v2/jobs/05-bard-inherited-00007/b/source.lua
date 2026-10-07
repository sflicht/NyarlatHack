return function(c)
local s=(c.state+1)%8
if s%4==0 then
return {dx=0,dy=0,state=s}
end
local n=#c.history
if n<1 then
return {dx=0,dy=0,state=s}
end
local idx=n
if s%4==1 and n>1 then
idx=n-1
elseif s%4==3 and n>2 then
idx=n-2
end
local e=c.history[idx]
if e==nil then
return {dx=0,dy=0,state=s}
end
local dx=0
local dy=0
if e.x>c.mx then dx=1 elseif e.x<c.mx then dx=-1 end
if e.y>c.my then dy=1 elseif e.y<c.my then dy=-1 end
return {dx=dx,dy=dy,state=s}
end
