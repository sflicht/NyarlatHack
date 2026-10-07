return function(c)
local s=c.state%8+1
local dx,dy=0,0
if s<6 then
local n,k=0,1
while k<=8 do
if c.history[k]==nil then break end
n=k
k=k+1
end
if n>0 then
local i=n
if s==1 and n>1 then i=n-1 end
if s==3 and n>2 then i=n-2 end
local p=c.history[i]
if p.x>c.mx then dx=1 elseif p.x<c.mx then dx=-1 end
if p.y>c.my then dy=1 elseif p.y<c.my then dy=-1 end
end
end
return {dx=dx,dy=dy,state=s}
end
