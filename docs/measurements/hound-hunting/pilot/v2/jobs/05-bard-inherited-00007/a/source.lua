return function(c)
local s=c.state+1
if s>1000000 then s=0 end
local beat=s%4
if beat==0 then return {dx=0,dy=0,state=s} end
local h=c.history
local prev=h[1]
local last=h[1]
for i=2,8 do
if h[i]~=nil then prev=last; last=h[i] end
end
local p=last
if beat==1 then p=prev end
if p==nil then return {dx=0,dy=0,state=s} end
local dx=0
local dy=0
if c.mx<p.x then dx=1 end
if c.mx>p.x then dx=-1 end
if c.my<p.y then dy=1 end
if c.my>p.y then dy=-1 end
return {dx=dx,dy=dy,state=s}
end
