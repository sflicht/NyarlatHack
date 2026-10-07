return function(c)
local s=c.state
if s==nil or s<0 or s>1000000 then s=0 end
local ns=s+1
if ns>1000000 then ns=0 end
local phase=s%24
if phase<3 then return {dx=0,dy=0,state=ns} end
local h=c.history
if h==nil or #h<1 then return {dx=0,dy=0,state=ns} end
local len=#h
local idx=len
if phase==3 and len>1 then idx=len-1 end
if phase==4 and len>2 then idx=len-2 end
local p=h[idx]
if p==nil then p=h[len] end
if p==nil then return {dx=0,dy=0,state=ns} end
if p.x==c.mx and p.y==c.my then p=h[len] end
local dx=0
local dy=0
if p.x>c.mx then dx=1 elseif p.x<c.mx then dx=-1 end
if p.y>c.my then dy=1 elseif p.y<c.my then dy=-1 end
return {dx=dx,dy=dy,state=ns}
end
