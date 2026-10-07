return function(c)
local st=c.state+1
if st>1000000 then st=0 end
local phase=st%5
if phase==0 then return {dx=0,dy=0,state=st} end
local h=c.history
local n=#h
local newest=h[n]
local echo=h[1]
if n>=5 then echo=h[n-4] end
local dx=0
local dy=0
local back=false
if n>=3 then
local ax=h[2].x-h[1].x
local ay=h[2].y-h[1].y
local bx=h[n].x-h[n-1].x
local by=h[n].y-h[n-1].y
if ax*bx+ay*by<0 then back=true end
end
if back then
local bx=h[n].x-h[n-1].x
local by=h[n].y-h[n-1].y
if bx~=0 then
dy=1
if phase%2==0 then dy=-1 end
else
dx=1
if phase%2==0 then dx=-1 end
end
else
local sx=echo.x-c.mx
local sy=echo.y-c.my
if sx>0 then dx=1 elseif sx<0 then dx=-1 end
if sy>0 then dy=1 elseif sy<0 then dy=-1 end
if phase==2 and dx~=0 then dy=0 end
if phase==3 and dy~=0 then dx=0 end
end
local ndx=newest.x-c.mx
local ndy=newest.y-c.my
local adx=ndx
if adx<0 then adx=-adx end
local ady=ndy
if ady<0 then ady=-ady end
local cheb=adx
if ady>cheb then cheb=ady end
if cheb<3 then
dx=0
dy=0
if ndx>0 then dx=-1 elseif ndx<0 then dx=1 end
if ndy>0 then dy=-1 elseif ndy<0 then dy=1 end
if dx==0 and dy==0 then
if phase%2==0 then dx=1 else dy=-1 end
end
else
local tx=ndx-dx
if tx<0 then tx=-tx end
local ty=ndy-dy
if ty<0 then ty=-ty end
local ncheb=tx
if ty>ncheb then ncheb=ty end
if ncheb<3 and ncheb<cheb then
dx=0
dy=0
end
end
return {dx=dx,dy=dy,state=st}
end
