return function(c)
  local s=(c.state+1)%1000000
  local n=#c.history
  if n<1 then return {dx=0,dy=0,state=s} end
  local phase=s%4
  if phase==0 then return {dx=0,dy=0,state=s} end
  local idx=n-(phase-1)
  if idx<1 then idx=1 end
  local p=c.history[idx]
  if p==nil then return {dx=0,dy=0,state=s} end
  local tx=p.x-c.mx
  local ty=p.y-c.my
  if tx==0 and ty==0 and idx<n then
    p=c.history[n]
    if p==nil then return {dx=0,dy=0,state=s} end
    tx=p.x-c.mx
    ty=p.y-c.my
  end
  local dx=0
  local dy=0
  if tx>0 then dx=1 elseif tx<0 then dx=-1 end
  if ty>0 then dy=1 elseif ty<0 then dy=-1 end
  return {dx=dx,dy=dy,state=s}
end
