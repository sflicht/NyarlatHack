return function(c)
local s=c.state+1
if s>1000000 then s=0 end
local h=c.history
local n=0
if h~=nil then n=#h end
if n<1 or s%4==0 then return {dx=0,dy=0,state=s} end
local i=n
if s%4==1 and n>1 then i=n-1 end
local e=h[i]
local dx=0
local dy=0
if e.x>c.mx then dx=1 elseif e.x<c.mx then dx=-1 end
if e.y>c.my then dy=1 elseif e.y<c.my then dy=-1 end
return {dx=dx,dy=dy,state=s}
end
