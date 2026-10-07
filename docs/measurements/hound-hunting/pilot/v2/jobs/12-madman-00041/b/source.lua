return function(c)
local s=c.state+1
if s>1000000 then s=0 end
local phase=s%8
if phase>4 then return {dx=0,dy=0,state=s} end
local n=#c.history
if n<1 then return {dx=0,dy=0,state=s} end
if n>8 then n=8 end
local idx=n
if phase==2 then idx=n-2 elseif phase==4 then idx=n-1 end
if idx<1 then idx=1 end
local p=c.history[idx]
local dx=0
local dy=0
if p.x>c.mx then dx=1 elseif p.x<c.mx then dx=-1 end
if p.y>c.my then dy=1 elseif p.y<c.my then dy=-1 end
if dx==0 and dy==0 and idx~=n then
p=c.history[n]
if p.x>c.mx then dx=1 elseif p.x<c.mx then dx=-1 end
if p.y>c.my then dy=1 elseif p.y<c.my then dy=-1 end
end
return {dx=dx,dy=dy,state=s}
end
