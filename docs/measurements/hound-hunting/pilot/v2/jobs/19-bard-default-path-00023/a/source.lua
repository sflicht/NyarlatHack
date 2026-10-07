return function(c)
  local s=c.state
  if s<0 or s>1000000 then s=0 end
  local ns=s+1
  if ns>1000000 then ns=0 end
  local beat=s%4
  if beat==0 then return {dx=0,dy=0,state=ns} end
  local h=c.history
  local n=0
  if h[1]~=nil then n=1 end
  if h[2]~=nil then n=2 end
  if h[3]~=nil then n=3 end
  if h[4]~=nil then n=4 end
  if h[5]~=nil then n=5 end
  if h[6]~=nil then n=6 end
  if h[7]~=nil then n=7 end
  if h[8]~=nil then n=8 end
  if n<1 then return {dx=0,dy=0,state=ns} end
  local i=n
  if beat==2 and n>1 then i=n-1 end
  if beat==3 and n>1 then i=n-1 end
  if beat==3 and n>3 then i=n-2 end
  local t=h[i]
  if t==nil or t.x==nil or t.y==nil then return {dx=0,dy=0,state=ns} end
  local dx=0
  local dy=0
  if t.x>c.mx then dx=1 elseif t.x<c.mx then dx=-1 end
  if t.y>c.my then dy=1 elseif t.y<c.my then dy=-1 end
  return {dx=dx,dy=dy,state=ns}
end
