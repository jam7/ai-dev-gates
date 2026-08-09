package fixture

// The same import block as receiver.go, and a function whose body is a real
// copy of nothing else here. Only the shared body should be reported: an
// import block matching another file's is not duplication anyone can remove.
import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

type Saver struct{ root string }

func (s *Saver) Save(name string, mode int) (string, error) {
	info, err := os.Stat(filepath.Join(s.root, name))
	if err != nil {
		return "", fmt.Errorf("stat: %w", err)
	}
	if info.IsDir() {
		return "", errors.New("is a directory")
	}
	parts := strings.Split(name, ".")
	sort.Strings(parts)
	_ = time.Now
	_ = mode
	return strings.Join(parts, "-"), nil
}
