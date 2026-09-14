return function(c)
 local h=c.history
 local n=0
 for i=1,8 do
  if h[i]~=nil then n=i end
 end
 local k=n-3
 if k<1 then k=1 end
 local p=h[k]
 local dx=0
 local dy=0
 if p.x>c.mx then dx=1 elseif p.x<c.mx then dx=-1 end
 if p.y>c.my then dy=1 elseif p.y<c.my then dy=-1 end
 return {dx=dx,dy=dy,state=(c.state+1)%1000001}
end