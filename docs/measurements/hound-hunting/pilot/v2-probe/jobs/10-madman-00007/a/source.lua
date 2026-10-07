return function(c)
  local s=(c.state+1)%1000001
  if s%4==0 then
    return {dx=0,dy=0,state=s}
  end
  local n=#c.history
  local back=1
  if n>2 and s%2==0 then
    back=2
  end
  local i=n-back
  if i<1 then
    i=1
  end
  local p=c.history[i]
  local dx=0
  local dy=0
  if p.x>c.mx then
    dx=1
  elseif p.x<c.mx then
    dx=-1
  end
  if p.y>c.my then
    dy=1
  elseif p.y<c.my then
    dy=-1
  end
  return {dx=dx,dy=dy,state=s}
end
