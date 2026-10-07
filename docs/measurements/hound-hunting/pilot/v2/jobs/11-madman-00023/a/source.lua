return function(c)
local s=c.state
if s<0 then s=0 end
if s>1000000 then s=0 end
local ns=s+1
if ns>1000000 then ns=0 end
local n=#c.history
if n<1 then return {dx=0,dy=0,state=ns} end
local m=s%8
if m>4 then return {dx=0,dy=0,state=ns} end
local lag=0
if m==2 or m==4 then lag=1 end
local idx=n-lag
if idx<1 then idx=1 end
local p=c.history[idx]
local dx=0
local dy=0
if p.x>c.mx then dx=1 elseif p.x<c.mx then dx=-1 end
if p.y>c.my then dy=1 elseif p.y<c.my then dy=-1 end
return {dx=dx,dy=dy,state=ns}
end
