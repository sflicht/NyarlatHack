return function(c)
local s=c.state+1
if s>1000000 then s=0 end
local dx=0
local dy=0
local phase=s%8
if phase>1 then
local n=1
if c.history[2]~=nil then n=2 end
if c.history[3]~=nil then n=3 end
if c.history[4]~=nil then n=4 end
if c.history[5]~=nil then n=5 end
if c.history[6]~=nil then n=6 end
if c.history[7]~=nil then n=7 end
if c.history[8]~=nil then n=8 end
local idx=n
if phase==2 then
idx=n-3
if idx<1 then idx=1 end
end
local t=c.history[idx]
if t~=nil then
if t.x>c.mx then dx=1 elseif t.x<c.mx then dx=-1 end
if t.y>c.my then dy=1 elseif t.y<c.my then dy=-1 end
end
end
return {dx=dx,dy=dy,state=s}
end
