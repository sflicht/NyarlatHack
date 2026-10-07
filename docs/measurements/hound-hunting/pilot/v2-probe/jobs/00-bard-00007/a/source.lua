return function(c)
local s=c.state+1
if s>11 then s=0 end
if s<3 then return {dx=0,dy=0,state=s} end
local n=#c.history
if n<1 then return {dx=0,dy=0,state=s} end
if n>8 then n=8 end
local idx=n
if s==3 then idx=1
elseif s%2==0 then
idx=n-1
if idx<1 then idx=1 end
end
local p=c.history[idx]
if p==nil then return {dx=0,dy=0,state=s} end
local dx=0
local dy=0
if p.x>c.mx then dx=1 elseif p.x<c.mx then dx=-1 end
if p.y>c.my then dy=1 elseif p.y<c.my then dy=-1 end
return {dx=dx,dy=dy,state=s}
end
