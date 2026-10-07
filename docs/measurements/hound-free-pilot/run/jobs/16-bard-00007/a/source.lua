return function(c)
local h=c.history
local n=#h
local now=h[n]
local echo=h[1]
local mx=c.mx
local my=c.my
local s=c.state+1
if s>1000000 then s=0 end
local cx=mx-now.x
if cx<0 then cx=-cx end
local cy=my-now.y
if cy<0 then cy=-cy end
local dx=0
local dy=0
if cx<=2 and cy<=2 then
if now.x>mx then dx=-1 elseif now.x<mx then dx=1 end
if now.y>my then dy=-1 elseif now.y<my then dy=1 end
else
local tx=echo.x
local ty=echo.y
if n>=2 then
tx=tx-(now.x-h[n-1].x)
ty=ty-(now.y-h[n-1].y)
end
if tx>mx then dx=1 elseif tx<mx then dx=-1 end
if ty>my then dy=1 elseif ty<my then dy=-1 end
if s%4==0 then dx=-dx dy=-dy end
end
if dx==0 and dy==0 then
if s%2==0 then dx=1 else dy=1 end
end
return {dx=dx,dy=dy,state=s}
end
