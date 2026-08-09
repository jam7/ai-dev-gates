package fixture

// A Go import block: its lines are bare paths, so duplicate detection has to
// drop the block rather than the lines.
import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

// A method: the receiver must not be counted as a parameter, and the reported
// name must be the method's, not the receiver's.
type Loader struct{ root string }

func (l *Loader) Load(name string, mode int) (string, error) {
	info, err := os.Stat(filepath.Join(l.root, name))
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

// A raw string holds a path verbatim; backticks must not desync the scanner.
func Raw() string {
	return `C:\some\path\file.txt`
}
